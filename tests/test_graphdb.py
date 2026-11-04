"""The knowledge graph in Neo4j: projection from the ledger views, sync, queries, CLI and auto-sync.

No live Neo4j here: the driver is faked. `carbonroom graphdb selftest` runs the Cypher against a real server.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from carbonroom import config
from carbonroom.cli import main
from carbonroom.graphdb import queries, store
from carbonroom.ingest import pipeline
from carbonroom.ledger import db
from carbonroom.ledger import graph as ledger_graph

REPO = Path(__file__).resolve().parents[1]
VIEW_LINKS = {(src, rel.upper(), dst) for src, rel, dst in re.findall(
    r"SELECT '(\w+)', [\w.]+, '(\w+)', '(\w+)'", (REPO / "contracts" / "schema.sql").read_text())}
VIEW_RELS = {rel for _, rel, _ in VIEW_LINKS}


@pytest.fixture
def full(seeded):
    later = config.seed_dir() / "later"
    pipeline.ingest_file(seeded, later / "2026-10_reno_electricity_ELB-RNO-2610.pdf", received_from="lena",
                         room="cr-site-reno", meta={"gap_id": "GAP-999"})  # answers a gap that doesn't exist
    pipeline.ingest_file(seeded, later / "2026-10_austin_electricity_ELB-AUS-2610-C.pdf", received_from="omar",
                         room="cr-site-austin")
    diesel = db.list_activities(seeded, period_id="2026-10", category="diesel")
    gap, _ = db.create_gap(seeded, kind="conflict", detail="INV-204 vs INV-204B", created_by="cr-checker",
                           period_id="2026-10", site_id="austin", refs={"activity_ids": [a["id"] for a in diesel]})
    db.resolve_gap(seeded, gap["id"], resolution="use INV-204B", resolved_by="omar")
    db.create_gap(seeded, kind="missing_doc", detail="no bill", created_by="cr-checker", period_id="2026-10",
                  site_id="reno")
    db.add_emission_factor(seeded, id="F-NWPP", set_version="v1", category="electricity", region="NWPP",
                           scope="2_location", factor="0.3", unit="kg CO2e/kWh", source_name="EPA eGRID",
                           source_edition="test")
    reno = db.list_activities(seeded, period_id="2026-10", site_id="reno")[0]
    db.add_calculation(seeded, activity_id=reno["id"], factor_id="F-NWPP", scope="2_location", co2e_kg="1",
                       code_version="t")
    db.record_approval(seeded, period_id="2026-10", approver_handle="grace", decision="REJECT", note="not yet")
    return seeded


def _rels(proj, rel):
    return {(r["src"], r["dst"]) for r in proj["relationships"] if r["type"] == rel}


# --- one graph model: the projection is exactly the ledger views ------------------------------------


def test_projection_is_exactly_the_ledger_views(full):
    proj = store.projection(full)
    view_nodes = {(r["type"], r["id"]) for r in full.execute("SELECT type, id FROM ledger_nodes")}
    assert set(proj["nodes"]) == view_nodes
    view_edges = ledger_graph.edges(full)
    assert len(proj["relationships"]) + proj["skipped"] == len(view_edges)
    assert proj["skipped"] == 1  # the ANSWERS link to GAP-999, which doesn't exist
    for r in proj["relationships"]:
        assert (r["src"][0], r["type"], r["dst"][0]) in VIEW_LINKS


def test_the_links_people_ask_about_are_there(full):
    proj = store.projection(full)
    old = next(a for a in db.list_activities(full) if a["quantity"] == "191300")
    new = next(a for a in db.list_activities(full) if a["quantity"] == "196800")
    assert (("activity", new["id"]), ("activity", old["id"])) in _rels(proj, "REPLACES")
    assert (("doc", old["source_doc_id"]), ("doc", new["source_doc_id"])) in _rels(proj, "SUPERSEDED_BY")
    assert (("activity", old["id"]), ("doc", old["source_doc_id"])) in _rels(proj, "EVIDENCED_BY")
    ins = db.list_instruments(full)[0]
    assert (("instrument", ins["id"]), ("site", "nimbus-cloud")) in _rels(proj, "CLAIMED_AGAINST")
    assert len(_rels(proj, "USES_FACTOR")) == 1 and len(_rels(proj, "RESOLVED_BY")) == 1


def test_nodes_carry_details_and_neo4j_safe_values(full):
    proj = store.projection(full)
    assert set(ledger_graph.NODE_TYPES) <= set(store.TYPE_LABELS)
    diesel = [p for (t, _), p in proj["nodes"].items() if t == "activity" and p.get("category") == "diesel"]
    assert {p.get("delivery_ref") for p in diesel} == {"DLV-7590", "DLV-7731"}
    assert all(isinstance(p["quantity"], str) for p in diesel)  # decimal strings, never floats
    for props in proj["nodes"].values():
        assert props["id"] and props.get("name")
        for value in props.values():
            assert isinstance(value, (str, int, float, bool)) or (
                isinstance(value, list) and value and all(isinstance(v, str) for v in value)), value


# --- sync -------------------------------------------------------------------------------------------


def test_sync_is_one_safe_rebuild(full):
    proj = store.projection(full)
    stmts = store.sync_statements(proj, {"event_id": 1})
    assert stmts[0][0] == "MATCH (n:CR) DETACH DELETE n"  # only Carbon Room nodes
    text = " ".join(q for q, _ in stmts)
    assert set(re.findall(r":CR:(\w+)", text)) <= set(store.LABELS)
    assert set(re.findall(r"\[r:(\w+)\]", text)) <= VIEW_RELS
    for (_, node_id) in proj["nodes"]:
        assert node_id not in text  # values are parameters, never query text
    assert sum(len(p["rows"]) for _, p in stmts if "rows" in p) == len(proj["nodes"]) + len(proj["relationships"])
    json.dumps([p for _, p in stmts])


class FakeTx:
    def __init__(self, log):
        self.log = log

    def run(self, query, params=None):
        self.log.append((query, params))
        return SimpleNamespace(consume=lambda: None)


class FakeSession:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, params=None):
        self.driver.schema.append(query)
        return SimpleNamespace(consume=lambda: None)

    def execute_write(self, work):
        self.driver.transactions += 1
        work(FakeTx(self.driver.writes))


class FakeDriver:
    def __init__(self, records=None):
        self.schema, self.writes, self.reads, self.transactions = [], [], [], 0
        self.records = records or []

    def session(self, database=None):
        return FakeSession(self)

    def execute_query(self, query, params, routing_=None, database_=None):
        self.reads.append((query, params, routing_))
        return SimpleNamespace(records=[SimpleNamespace(data=lambda r=r: r) for r in self.records])

    def close(self):
        pass


def test_store_writes_in_one_transaction_and_reads_routed_read(full):
    from neo4j import RoutingControl

    driver = FakeDriver(records=[{"n": 1}])
    neo = store.Neo4jStore(driver=driver)
    result = store.sync(full, neo)
    assert driver.transactions == 1 and len(driver.schema) == len(store.LABELS) + 1
    assert result["nodes"] == len(store.projection(full)["nodes"]) and result["skipped_links"] == 1
    assert neo.read("MATCH (n) RETURN 1 AS n") == [{"n": 1}]
    assert driver.reads[-1][2] == RoutingControl.READ


def test_driver_silences_unknown_link_notices(monkeypatch):
    # An empty ledger has no gap links yet; Neo4j must not print "relationship type does not exist" on every query.
    import neo4j

    seen = {}
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda uri, **kw: seen.update(kw, uri=uri) or "drv")
    assert store.Neo4jStore(uri="bolt://x:7687").driver == "drv"
    assert seen["notifications_disabled_classifications"] == [neo4j.NotificationDisabledClassification.UNRECOGNIZED]
    assert seen["connection_timeout"] == 5.0


def test_sync_if_enabled_respects_the_mode(full, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(store, "sync", lambda conn, neo=None: calls.append(1) or {"nodes": 0})
    monkeypatch.setenv("CR_GRAPH", "off")
    assert store.sync_if_enabled(full) is None and calls == []
    monkeypatch.setenv("CR_GRAPH", "auto")
    monkeypatch.setattr(store, "reachable", lambda uri=None, timeout=0.4: False)
    assert store.sync_if_enabled(full) is None and capsys.readouterr().err == ""
    monkeypatch.setenv("CR_GRAPH", "on")
    assert store.sync_if_enabled(full) is None and "isn't reachable" in capsys.readouterr().err
    monkeypatch.setattr(store, "reachable", lambda uri=None, timeout=0.4: True)
    assert store.sync_if_enabled(full) == {"nodes": 0} and calls == [1]


def test_a_failing_sync_never_breaks_the_caller(full, monkeypatch, capsys):
    monkeypatch.setenv("CR_GRAPH", "auto")
    monkeypatch.setattr(store, "reachable", lambda uri=None, timeout=0.4: True)
    monkeypatch.setattr(store, "sync", lambda conn, neo=None: (_ for _ in ()).throw(RuntimeError("auth failed")))
    assert store.sync_if_enabled(full) is None and "auth failed" in capsys.readouterr().err


def test_cli_syncs_after_any_command_that_wrote(env, monkeypatch):
    synced = []
    monkeypatch.setenv("CR_GRAPH", "auto")
    monkeypatch.setattr(store, "reachable", lambda uri=None, timeout=0.4: True)
    monkeypatch.setattr(store, "sync", lambda conn, neo=None: synced.append(1) or {"nodes": 1})
    assert main(["seed"]) == 0 and synced == [1]
    assert main(["ledger", "show", "--period", "2026-10"]) == 0 and synced == [1]  # read-only: no sync
    bill = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    assert main(["ingest", str(bill), "--from", "lena"]) == 0 and synced == [1, 1]


def test_collect_node_reports_graph_sync(env):
    from carbonroom.ingest import batch

    out = batch.collect_node({"files": [str(config.seed_dir() / "docs")], "db_path": str(env / "n.db")})
    assert out["ingest_summaries"][0]["graph_synced"] is False  # CR_GRAPH=off in tests


# --- queries ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["WHY", "CONFLICTS", "GAPS_BY_OWNER", "FIND"])
def test_cypher_is_well_formed_read_only_and_uses_only_view_links(name):
    text = getattr(queries, name)
    for open_, close in ("()", "[]", "{}"):
        assert text.count(open_) == text.count(close), (name, open_)
    assert "{{" not in text and "}}" not in text
    assert not queries._WRITE_CLAUSES.search(text)
    assert set(re.findall(r"\[:(\w+)\]", text)) <= VIEW_RELS  # never a link name the views don't produce
    assert set(re.findall(r"\((?:\w+)?:(\w+)", text)) - {"CR"} <= set(store.LABELS)


def test_read_only_guard():
    neo = store.Neo4jStore(driver=FakeDriver())
    for cypher in ("MATCH (n) SET n.x = 1", "CREATE (n)", "MATCH (n) DETACH DELETE n", "MERGE (n:X)",
                   "CALL db.labels()", "LOAD CSV FROM 'x' AS r RETURN r"):
        with pytest.raises(queries.QueryError):
            queries.read_only(neo, cypher)
    assert queries.read_only(neo, "MATCH (n:CR) RETURN count(n) AS n") == []


def test_why_answers_in_one_sentence():
    row = {"site": {"id": "reno", "name": "Reno Office"}, "period_known": True, "owner": ["lena"],
           "expects": [{"category": "electricity", "frequency": "monthly"}], "activities": [], "instruments": [],
           "gaps": [{"id": "GAP-012", "kind": "missing_doc", "status": "OPEN", "detail": "bill missing", "about": []}]}
    answer = queries.why(store.Neo4jStore(driver=FakeDriver(records=[row])), "reno", "2026-10")
    assert answer["missing"] == ["electricity"]
    assert answer["summary"] == ("No document for Reno Office 2026-10 has reached the ledger. Open gaps: GAP-012 "
                                 "missing_doc: bill missing. Still missing: electricity (owner @lena).")
    row = {**row, "activities": [{"category": "electricity", "quantity": "15080", "unit": "kWh",
                                  "status": "UNVERIFIED", "documents": ["ELB-RNO-2610"]}], "gaps": []}
    answer = queries.why(store.Neo4jStore(driver=FakeDriver(records=[row])), "reno", "2026-10")
    assert answer["summary"] == ("1 document(s) for Reno Office 2026-10: ELB-RNO-2610. Recorded: electricity 15080 kWh "
                                 "(UNVERIFIED).")


def test_graphdb_commands_explain_how_to_start_neo4j(full, monkeypatch, capsys):
    monkeypatch.setattr(store, "reachable", lambda uri=None, timeout=0.4: False)
    assert main(["graphdb", "why", "reno", "2026-10"]) == 2
    assert "docker compose -f infra/neo4j/docker-compose.yml up -d" in capsys.readouterr().err
    assert main(["graphdb", "status"]) == 0 and "reachable=False" in capsys.readouterr().out
