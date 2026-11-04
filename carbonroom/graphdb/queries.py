"""Questions the graph database answers (Cypher on Neo4j, read-only).

The graph has the same node types and links as the ledger's views (carbonroom/ledger/graph.py), with the
link names upper-cased: EVIDENCED_BY, AT_SITE, IN_PERIOD, REPLACES, SUPERSEDED_BY, RECEIVED_FROM,
POSTED_IN, COLLECTED_IN, ANSWERS, CLAIMED_AGAINST, OF, USES_FACTOR, ABOUT, ABOUT_SITE, OWNED_BY,
RAISED_IN, RESOLVED_BY, HAS_ROOM, FOR_SITE, FOR_PERIOD, BY, APPROVED_BY.

Tracing a number and "what depends on this bill" are already answered offline by `carbonroom ledger trace`
and `ledger impact`. Neo4j adds:
  why(site, period)    "Why didn't you consider the Reno bill for October?" - what was recorded from which
                        documents, which gaps are open, what monthly evidence is still missing, as one sentence
  conflicts(period)    fuel deliveries with two different quantities
  gaps_by_owner()      open gaps per person
  find(text)           search ids, names, doc numbers, file names, excerpts, gap details
  read_only(cypher)    any read-only Cypher, for agents (writes are refused)
`selftest` runs every one of them against a live server.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from carbonroom.graphdb.store import CR_LABEL, Neo4jStore, projection, sync
from carbonroom.ledger import db

WHY = f"""
MATCH (s:{CR_LABEL}:Site {{id: $site}})
OPTIONAL MATCH (pe:{CR_LABEL}:Period {{id: $period}})
RETURN s {{.id, .name}} AS site,
  pe IS NOT NULL AS period_known,
  [(s)-[:OWNED_BY]->(ow:Person) | ow.id] AS owner,
  [(s)<-[:FOR_SITE]-(ex:Expected) | ex {{.category, .frequency}}] AS expects,
  [(s)<-[:AT_SITE]-(a:Activity)-[:IN_PERIOD]->(:Period {{id: $period}})
     | a {{.id, .category, .quantity, .unit, .status,
          documents: [(a)-[:EVIDENCED_BY]->(d:Document) | coalesce(d.doc_ref, d.original_name, d.id)]}}] AS activities,
  [(s)<-[:CLAIMED_AGAINST]-(i:Instrument)-[:IN_PERIOD]->(:Period {{id: $period}})
     | i {{.id, .kind, .mwh, .region, .vintage, .status,
          documents: [(i)-[:EVIDENCED_BY]->(d2:Document) | coalesce(d2.doc_ref, d2.id)]}}] AS instruments,
  [(s)<-[:ABOUT_SITE]-(g:Gap)-[:IN_PERIOD]->(:Period {{id: $period}})
     | g {{.id, .kind, .status, .detail, about: [(g)-[:ABOUT]->(x) | coalesce(x.doc_ref, x.id)]}}] AS gaps
"""

CONFLICTS = f"""
MATCH (a:{CR_LABEL}:Activity)
WHERE a.delivery_ref IS NOT NULL AND a.status <> 'SUPERSEDED' AND ($period IS NULL OR a.period_id = $period)
WITH a.delivery_ref AS delivery, collect(a {{.id, .quantity, .unit, .doc_ref, .status}}) AS claims,
     count(DISTINCT a.quantity) AS quantities
WHERE quantities > 1
RETURN delivery, claims
ORDER BY delivery
"""

GAPS_BY_OWNER = f"""
MATCH (g:{CR_LABEL}:Gap {{status: 'OPEN'}})
OPTIONAL MATCH (g)-[:OWNED_BY]->(p:Person)
RETURN coalesce(p.id, 'unassigned') AS owner, collect(g {{.id, .kind, .detail}}) AS gaps
ORDER BY owner
"""

FIND = f"""
MATCH (n:{CR_LABEL})
WHERE any(k IN ['id', 'name', 'doc_ref', 'original_name', 'excerpt', 'detail', 'certificate_id', 'region']
          WHERE toLower(toString(n[k])) CONTAINS toLower($text))
RETURN head([l IN labels(n) WHERE l <> '{CR_LABEL}']) AS label, n.id AS id, coalesce(n.name, n.doc_ref, n.detail) AS summary
ORDER BY label, id
LIMIT $limit
"""

_WRITE_CLAUSES = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|CALL\s*\{|CALL\s+(db|dbms|apoc|gds)\.)",
    re.IGNORECASE,
)


class QueryError(ValueError):
    pass


def why(store: Neo4jStore, site: str, period: str) -> dict[str, Any] | None:
    rows = store.read(WHY, {"site": site, "period": period})
    if not rows:
        return None
    answer = rows[0]
    have = {a["category"] for a in answer["activities"] if a.get("status") != "SUPERSEDED"}
    monthly = sorted({e["category"] for e in answer["expects"] if e.get("frequency") == "monthly"})
    answer["missing"] = [c for c in monthly if c not in have]
    docs: list[str] = []
    for item in answer["activities"] + answer["instruments"]:
        docs += [d for d in item.get("documents") or [] if d not in docs]
    for g in answer["gaps"]:
        docs += [d for d in g.get("about") or [] if not d.startswith(("ACT-", "INS-")) and d not in docs]
    answer["documents"] = docs
    answer["summary"] = _why_text(answer, period)
    return answer


def _why_text(a: dict[str, Any], period: str) -> str:
    site = a["site"]["name"]
    owner = f"@{a['owner'][0]}" if a["owner"] else "the site owner"
    if not a["documents"]:
        text = f"No document for {site} {period} has reached the ledger."
    else:
        text = f"{len(a['documents'])} document(s) for {site} {period}: {', '.join(a['documents'])}."
    used = [f"{x['category']} {x['quantity']} {x['unit']} ({x['status']})" for x in a["activities"]]
    used += [f"{x['kind']} {x['mwh']} MWh ({x['status']})" for x in a["instruments"]]
    if used:
        text += " Recorded: " + "; ".join(used) + "."
    open_gaps = [g for g in a["gaps"] if g["status"] == "OPEN"]
    if open_gaps:
        text += " Open gaps: " + "; ".join(f"{g['id']} {g['kind']}: {g['detail']}" for g in open_gaps) + "."
    if a["missing"]:
        text += f" Still missing: {', '.join(a['missing'])} (owner {owner})."
    return text


def conflicts(store: Neo4jStore, period: str | None = None) -> list[dict[str, Any]]:
    return store.read(CONFLICTS, {"period": period})


def gaps_by_owner(store: Neo4jStore) -> list[dict[str, Any]]:
    return store.read(GAPS_BY_OWNER)


def find(store: Neo4jStore, text: str, limit: int = 25) -> list[dict[str, Any]]:
    return store.read(FIND, {"text": text, "limit": int(limit)})


def read_only(store: Neo4jStore, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if _WRITE_CLAUSES.search(cypher):
        raise QueryError("only read-only Cypher is allowed here (no CREATE/MERGE/SET/DELETE/...)")
    return store.read(cypher, params or {})


def selftest(conn: sqlite3.Connection, store: Neo4jStore) -> list[tuple[str, bool, str]]:
    """Sync, then run every query against the live server. Returns (name, ok, detail) rows."""
    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn, expect=None):
        try:
            value = fn()
            ok = expect(value) if expect else True
            results.append((name, bool(ok), "" if ok else f"unexpected result: {str(value)[:200]}"))
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            results.append((name, False, f"{type(exc).__name__}: {str(exc)[:300]}"))

    proj = projection(conn)
    check("sync", lambda: sync(conn, store), lambda r: r["nodes"] == len(proj["nodes"]))
    check("node count matches the ledger views",
          lambda: read_only(store, f"MATCH (n:{CR_LABEL}) RETURN count(n) AS n"),
          lambda r: r[0]["n"] == len(proj["nodes"]))
    check("link count matches the ledger views",
          lambda: read_only(store, f"MATCH (:{CR_LABEL})-[r]->(:{CR_LABEL}) RETURN count(r) AS n"),
          lambda r: r[0]["n"] == len(proj["relationships"]))
    evidenced = sum(1 for r in proj["relationships"] if r["type"] == "EVIDENCED_BY" and r["src"][0] == "activity")
    check("every number links to its bill",
          lambda: read_only(store, "MATCH p = (:Activity)-[:EVIDENCED_BY]->(:Document) RETURN count(p) AS n"),
          lambda r: r[0]["n"] == evidenced)
    for site in db.list_sites(conn):
        for period in db.list_periods(conn):
            check(f"why {site['id']} {period['id']}", lambda s=site["id"], p=period["id"]: why(store, s, p),
                  lambda r: r is not None and "summary" in r)
    deliveries: dict[str, set[str]] = {}
    for (node_type, _), props in proj["nodes"].items():
        if node_type == "activity" and props.get("delivery_ref") and props.get("status") != "SUPERSEDED":
            deliveries.setdefault(props["delivery_ref"], set()).add(props["quantity"])
    expected = sorted(d for d, qs in deliveries.items() if len(qs) > 1)
    check("conflicts", lambda: conflicts(store), lambda r: sorted(x["delivery"] for x in r) == expected)
    check("gaps by owner", lambda: gaps_by_owner(store))
    check("find", lambda: find(store, "a"))
    check("read-only guard", lambda: _expect_refused(store))
    return results


def _expect_refused(store: Neo4jStore) -> bool:
    try:
        read_only(store, "MATCH (n) SET n.x = 1")
    except QueryError:
        return True
    raise AssertionError("a write query was not refused")
