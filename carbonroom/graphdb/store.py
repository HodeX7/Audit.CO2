"""The knowledge graph in a graph database (Neo4j), built from the ledger's graph views.

One graph model: the `ledger_nodes` / `ledger_edges` views in contracts/schema.sql (see
carbonroom/ledger/graph.py) define every node and link. This module copies exactly that graph into Neo4j:
the same node types, link names and ids, plus each node's useful details as properties. Neo4j then adds
Cypher for agents, the visual browser for the demo, and the questions in graphdb/queries.py.

Design
  * SQLite stays the system of record (honesty triggers, append-only). Neo4j holds a copy that can be
    rebuilt at any time.
  * Each sync is ONE write transaction: remove every Carbon Room node (label `CR`), then recreate the graph
    with UNWIND + MERGE. Readers see the old graph or the new one, never a mix. The ledger itself never
    deletes; only this disposable copy is rebuilt. At this scale (hundreds of rows) it takes well under a
    second; an incremental sync by event id is the next step if it ever matters.
  * Every node carries the extra label `CR`, so nothing else in a Neo4j instance is touched.
  * Node labels come from a fixed map (TYPE_LABELS) and link types are the view's `rel` upper-cased and
    checked against [A-Z_]+; every value travels as a query parameter.

Settings: CR_GRAPH = auto (default: sync when Neo4j answers) | on (warn when it doesn't) | off,
NEO4J_URI (bolt://localhost:7687), NEO4J_USER (neo4j), NEO4J_PASSWORD, NEO4J_DATABASE (neo4j).
Start a local Neo4j with infra/neo4j/docker-compose.yml.
"""

from __future__ import annotations

import re
import socket
import sqlite3
import sys
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from carbonroom import config
from carbonroom.ledger import db
from carbonroom.ledger import graph as ledger_graph

CR_LABEL = "CR"
META_LABEL = "CRMeta"
TYPE_LABELS = {
    "site": "Site", "period": "Period", "doc": "Document", "activity": "Activity", "instrument": "Instrument",
    "gap": "Gap", "calculation": "Calculation", "factor": "Factor", "expected": "Expected",
    "approval": "Approval", "person": "Person", "room": "Room", "run": "Run", "close": "Close",
}
LABELS = tuple(TYPE_LABELS.values())
_REL = re.compile(r"^[A-Z_]+$")
ACTIVITY_EXTRA = ("pue", "wue_l_per_kwh", "cloud_region", "delivery_ref", "delivery_date", "meter_id",
                  "original_quantity", "original_unit", "conversion", "doc_ref", "proposer")


class GraphError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------
# The projection: ledger views -> nodes and relationships (pure, testable without Neo4j)
# ---------------------------------------------------------------------------------------------------


def _clean(props: dict[str, Any]) -> dict[str, Any]:
    """Neo4j properties: primitives or non-empty lists of strings; drop None, empty lists and maps."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if v is None or v == [] or isinstance(v, dict):
            continue
        if isinstance(v, (list, tuple)):
            v = [str(x) for x in v if x is not None]
            if not v:
                continue
        elif not isinstance(v, (str, int, float, bool)):
            v = str(v)
        out[k] = v
    return out


def _details(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    """Per-node properties beyond the view's label/status, read from the ledger tables."""
    d: dict[tuple[str, str], dict[str, Any]] = {}
    for s in db.list_sites(conn):
        d[("site", s["id"])] = {"name": s["name"], "kind": s["kind"], "region": s["region"],
                                "grid_subregion": s["grid_subregion"], "aliases": s["aliases"]}
    for p in db.list_periods(conn):
        d[("period", p["id"])] = {"factor_set_version": p["factor_set_version"], "closed_at": p["closed_at"]}
    for doc in db.list_source_docs(conn):
        meta = doc["meta"] or {}
        d[("doc", doc["id"])] = {"doc_ref": doc["doc_ref"], "original_name": doc["original_name"], "path": doc["path"],
                                 "sha256": doc["sha256"], "kind": doc["kind"], "received_at": doc["received_at"],
                                 "page_count": doc["page_count"], "proposer": meta.get("proposer"),
                                 "notes": meta.get("notes")}
    for a in db.list_activities(conn):
        extra = a["extra"] or {}
        d[("activity", a["id"])] = {"category": a["category"], "quantity": a["quantity"], "unit": a["unit"],
                                    "excerpt": a["excerpt"], "locator": a["excerpt_locator"],
                                    "excerpt_sha256": a["excerpt_sha256"], "status_reason": a["status_reason"],
                                    "site_id": a["site_id"], "unverified_fields": extra.get("unverified_fields"),
                                    **{k: extra.get(k) for k in ACTIVITY_EXTRA}}
    for i in db.list_instruments(conn):
        d[("instrument", i["id"])] = {"kind": i["kind"], "mwh": i["mwh"], "region": i["region"], "vintage": i["vintage"],
                                      "certificate_id": i["certificate_id"], "quality_flags": i["quality_flags"],
                                      "excerpt": i["excerpt"], "locator": i["excerpt_locator"]}
    for g in db.list_gaps(conn):
        d[("gap", g["id"])] = {"kind": g["kind"], "detail": g["detail"], "owner": g["owner_handle"],
                               "resolution": g["resolution"], "created_at": g["created_at"],
                               "resolved_at": g["resolved_at"], "thread_id": g["thread_id"]}
    for f in db.list_emission_factors(conn):
        d[("factor", f["id"])] = {"set_version": f["set_version"], "category": f["category"], "region": f["region"],
                                  "scope": f["scope"], "factor": f["factor"], "unit": f["unit"],
                                  "source_name": f["source_name"], "source_edition": f["source_edition"]}
    for c in db.list_calculations(conn):
        d[("calculation", c["id"])] = {"scope": c["scope"], "co2e_kg": c["co2e_kg"], "computed_at": c["computed_at"],
                                       "code_version": c["code_version"]}
    for e in db.list_expected_documents(conn):
        d[("expected", e["id"])] = {"category": e["category"], "doc_kind": e["doc_kind"], "frequency": e["frequency"]}
    for row in conn.execute("SELECT * FROM approvals"):
        d[("approval", row["id"])] = {"decision": row["decision"], "note": row["note"], "at": row["at"],
                                      "report_sha256": row["report_sha256"]}
    for c in db.list_closes(conn):
        d[("close", c["id"])] = {"version": c["version"], "phase": c["phase"], "factor_set": c["factor_set"],
                                 "started_at": c["started_at"], "published_at": c["published_at"],
                                 "published_message_id": c["published_message_id"]}
    for row in conn.execute("SELECT * FROM events WHERE action = 'batch_finished'"):
        detail = db.row_to_dict(row)["detail"] or {}
        d[("run", row["ref"])] = {"summary_text": detail.get("summary_text"), "finished_at": detail.get("finished_at")}
    return d


def projection(conn: sqlite3.Connection) -> dict[str, Any]:
    """The ledger's graph (from the views) as Neo4j-ready nodes and relationships."""
    details = _details(conn)
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    for row in conn.execute("SELECT * FROM ledger_nodes"):
        node_type, node_id = row["type"], row["id"]
        if node_type not in TYPE_LABELS or node_id is None:
            continue
        base = {"id": node_id, "type": node_type, "label": row["label"], "name": row["label"],
                "status": row["status"], "period_id": row["period_id"]}
        nodes[(node_type, node_id)] = _clean({**base, **details.get((node_type, node_id), {}), "id": node_id})
    rels: list[dict[str, Any]] = []
    skipped = 0
    for e in ledger_graph.edges(conn):
        src, dst = (e["src_type"], e["src_id"]), (e["dst_type"], e["dst_id"])
        rel = str(e["rel"]).upper()
        if src not in nodes or dst not in nodes or not _REL.match(rel):
            skipped += 1  # e.g. an upload naming a gap id that doesn't exist (yet)
            continue
        rels.append({"type": rel, "src": src, "dst": dst, "props": _clean({"detail": e["detail"]})})
    return {"nodes": nodes, "relationships": rels, "skipped": skipped}


def counts(proj: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for (node_type, _) in proj["nodes"]:
        label = TYPE_LABELS[node_type]
        out[label] = out.get(label, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------------------------------


def mode() -> str:
    value = (config.env("CR_GRAPH", "auto") or "auto").lower()
    return value if value in ("auto", "on", "off") else "auto"


def settings() -> dict[str, str]:
    return {
        "uri": config.env("NEO4J_URI", "bolt://localhost:7687"),
        "user": config.env("NEO4J_USER", "neo4j"),
        "password": config.env("NEO4J_PASSWORD", "carbonroom-local"),
        "database": config.env("NEO4J_DATABASE", "neo4j"),
    }


def reachable(uri: str | None = None, timeout: float = 0.4) -> bool:
    """Cheap TCP check so commands never wait on a Neo4j that isn't running."""
    parsed = urlparse(uri or settings()["uri"])
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 7687), timeout=timeout):
            return True
    except OSError:
        return False


def schema_statements() -> list[str]:
    stmts = [f"CREATE CONSTRAINT cr_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
             for label in LABELS]
    stmts.append(f"CREATE INDEX cr_label_id IF NOT EXISTS FOR (n:{CR_LABEL}) ON (n.id)")
    return stmts


def sync_statements(proj: dict[str, Any], meta: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The full rebuild as (cypher, params) pairs, run in one write transaction."""
    stmts: list[tuple[str, dict[str, Any]]] = [
        (f"MATCH (n:{CR_LABEL}) DETACH DELETE n", {}),
        (f"MATCH (m:{META_LABEL}) DETACH DELETE m", {}),
    ]
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (node_type, node_id), props in proj["nodes"].items():
        by_label[TYPE_LABELS[node_type]].append({"id": node_id, "props": props})
    for label in sorted(by_label):
        assert label in LABELS
        stmts.append((f"UNWIND $rows AS row MERGE (n:{CR_LABEL}:{label} {{id: row.id}}) SET n += row.props",
                      {"rows": by_label[label]}))
    by_shape: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in proj["relationships"]:
        by_shape[(r["type"], TYPE_LABELS[r["src"][0]], TYPE_LABELS[r["dst"][0]])].append(
            {"src": r["src"][1], "dst": r["dst"][1], "props": r["props"]})
    for (rel, src, dst) in sorted(by_shape):
        assert _REL.match(rel) and src in LABELS and dst in LABELS
        stmts.append((
            f"UNWIND $rows AS row MATCH (a:{CR_LABEL}:{src} {{id: row.src}}) "
            f"MATCH (b:{CR_LABEL}:{dst} {{id: row.dst}}) MERGE (a)-[r:{rel}]->(b) SET r += row.props",
            {"rows": by_shape[(rel, src, dst)]},
        ))
    stmts.append((f"CREATE (m:{META_LABEL}) SET m = $meta", {"meta": meta}))
    return stmts


class Neo4jStore:
    """Thin wrapper around the official neo4j driver (Apache-2.0)."""

    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None,
                 database: str | None = None, driver: Any = None):
        s = settings()
        self.uri = uri or s["uri"]
        self.user = user or s["user"]
        self.password = password or s["password"]
        self.database = database or s["database"]
        self._driver = driver

    @property
    def driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase, NotificationDisabledClassification

            # A ledger with no gaps yet has no ABOUT / ABOUT_SITE links, so Neo4j would warn "relationship type
            # does not exist" on every why query. Normal, not a typo (test_graphdb checks every query uses only
            # link names the views produce), so those notices are switched off; real errors still raise.
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password), connection_timeout=5.0,
                notifications_disabled_classifications=[NotificationDisabledClassification.UNRECOGNIZED],
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def ensure_schema(self) -> None:
        with self.driver.session(database=self.database) as session:
            for stmt in schema_statements():  # schema changes can't share a transaction with data writes
                session.run(stmt).consume()

    def write(self, statements: list[tuple[str, dict[str, Any]]]) -> None:
        def work(tx):
            for query, params in statements:
                tx.run(query, params).consume()

        with self.driver.session(database=self.database) as session:
            session.execute_write(work)

    def read(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from neo4j import RoutingControl

        result = self.driver.execute_query(query, params or {}, routing_=RoutingControl.READ, database_=self.database)
        return [record.data() for record in result.records]


def _max_event_id(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0])


def sync(conn: sqlite3.Connection, store: Neo4jStore | None = None) -> dict[str, Any]:
    """Rebuild the Neo4j copy of the ledger's graph. Returns what was written."""
    proj = projection(conn)
    meta = {"synced_at": config.now_iso(), "event_id": _max_event_id(conn), "nodes": len(proj["nodes"]),
            "relationships": len(proj["relationships"]), "skipped_links": proj["skipped"]}
    own = store is None
    store = store or Neo4jStore()
    try:
        store.ensure_schema()
        store.write(sync_statements(proj, meta))
    finally:
        if own:
            store.close()
    return {**meta, "counts": counts(proj)}


def sync_if_enabled(conn: sqlite3.Connection, *, quiet: bool = False) -> dict[str, Any] | None:
    """Called after ledger writes. Never fails the caller: the ledger is the truth, the graph can wait."""
    m = mode()
    if m == "off":
        return None
    if not reachable():
        if m == "on" and not quiet:
            print(f"warning: CR_GRAPH=on but Neo4j isn't reachable at {settings()['uri']}; graph not updated",
                  file=sys.stderr)
        return None
    try:
        return sync(conn)
    except Exception as exc:  # noqa: BLE001 - report, don't break ingestion
        if not quiet:
            print(f"warning: knowledge graph sync failed: {exc}", file=sys.stderr)
        return None


def status(conn: sqlite3.Connection, store: Neo4jStore | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"mode": mode(), "uri": settings()["uri"], "reachable": reachable(),
                           "ledger_event_id": _max_event_id(conn)}
    if not out["reachable"]:
        return out
    own = store is None
    store = store or Neo4jStore()
    try:
        rows = store.read(f"MATCH (m:{META_LABEL}) RETURN m.synced_at AS synced_at, m.event_id AS event_id, "
                          "m.nodes AS nodes, m.relationships AS relationships")
        label_counts = store.read(f"MATCH (n:{CR_LABEL}) UNWIND [l IN labels(n) WHERE l <> '{CR_LABEL}'] AS label "
                                  "RETURN label, count(*) AS n ORDER BY label")
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out
    finally:
        if own:
            store.close()
    meta = rows[0] if rows else {}
    out.update(meta)
    out["counts"] = {r["label"]: r["n"] for r in label_counts}
    out["in_sync"] = bool(meta) and meta.get("event_id") == out["ledger_event_id"]
    return out
