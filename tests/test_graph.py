"""The ledger as a knowledge graph: live views, recursive traversal, lineage, impact, exports."""

from __future__ import annotations

import json
import re

import pytest

from carbonroom import config
from carbonroom.cli import main
from carbonroom.ingest import pipeline
from carbonroom.ledger import db, graph

AUSTIN_OCT = "ACT-0739d5932d"  # 191,300 kWh, from ELB-AUS-2610 (ids are deterministic)


def _corrected_bill(conn):
    return pipeline.ingest_file(conn, config.seed_dir() / "later" / "2026-10_austin_electricity_ELB-AUS-2610-C.pdf",
                                received_from="omar", room="cr-site-austin")


def _with_calculation(conn):
    db.add_emission_factor(conn, id="F-TEST", set_version="v-test", category="electricity", region="ERCT",
                           scope="2_location", factor="0.4", unit="kg CO2e/kWh", source_name="test source",
                           source_edition="test edition")
    return db.add_calculation(conn, activity_id=AUSTIN_OCT, factor_id="F-TEST", scope="2_location",
                              co2e_kg="76520", code_version="test")


def test_every_activity_is_wired_to_its_doc_site_and_period(seeded):
    rels = {}
    for e in graph.edges(seeded):
        if e["src_type"] == "activity":
            rels.setdefault(e["src_id"], []).append(e["rel"])
    assert len(rels) == 10
    assert all(sorted(r) == ["at_site", "evidenced_by", "in_period"] for r in rels.values())
    (ev,) = [e for e in graph.edges(seeded, "activity", AUSTIN_OCT, "out") if e["rel"] == "evidenced_by"]
    assert ev["detail"] == "page=1;line=10"  # the locator rides on the edge


def test_graph_is_live_no_sync_step(seeded):
    before = len(graph.edges(seeded))
    r = pipeline.ingest_file(seeded, config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf",
                             received_from="lena", room="cr-site-reno")
    assert len(graph.edges(seeded)) == before + 5  # activity: evidenced_by, at_site, in_period; doc: received_from, posted_in
    assert graph.node(seeded, "activity", r["activities"][0]["id"])["label"] == "electricity 15080 kWh"


def test_resolve_what_a_human_types(seeded):
    doc_id = db.find_source_docs_by_ref(seeded, "ELB-AUS-2610")[0]["id"]
    assert graph.resolve(seeded, "ELB-AUS-2610") == ("doc", doc_id)
    assert graph.resolve(seeded, doc_id) == ("doc", doc_id)
    assert graph.resolve(seeded, f"doc:{doc_id}") == ("doc", doc_id)
    assert graph.resolve(seeded, "@lena") == ("person", "lena")
    assert graph.resolve(seeded, "austin") == ("site", "austin")
    assert graph.resolve(seeded, "2026-10") == ("period", "2026-10")
    assert graph.resolve(seeded, "cr-site-reno") == ("room", "cr-site-reno")
    assert graph.resolve(seeded, AUSTIN_OCT) == ("activity", AUSTIN_OCT)
    with pytest.raises(db.LedgerError):
        graph.resolve(seeded, "XYZ-data-centre-report")


def test_lineage_answers_where_did_this_number_come_from(seeded):
    db.set_activity_status(seeded, AUSTIN_OCT, "VERIFIED", actor="cr-checker")
    calc = _with_calculation(seeded)
    _corrected_bill(seeded)
    gap, _ = db.create_gap(seeded, kind="excerpt_mismatch", detail="bill replaced; reopened", created_by="cr-checker",
                           period_id="2026-10", site_id="austin", refs={"activity_ids": [AUSTIN_OCT]})
    data = graph.lineage(seeded, AUSTIN_OCT)
    text = data["text"]
    assert text.startswith("191,300 kWh electricity · Austin Plant · 2026-10 · VERIFIED")
    assert 'page 1, line 10: "Total energy used this period: 191,300 kWh"' in text
    assert "ELB-AUS-2610 (DOC-" in text and "sent by @omar in cr-site-austin" in text
    assert "replaced by ELB-AUS-2610-C" in text and "corrected value: ACT-" in text
    assert "76520 kg CO2e" in text and "test source test edition" in text
    assert gap["id"] in text
    assert [d["doc_ref"] for d in data["document_chain"]] == ["ELB-AUS-2610", "ELB-AUS-2610-C"]
    assert graph.lineage(seeded, calc["id"])["calculations"][0]["id"] == calc["id"]  # from the CO2e number too
    with pytest.raises(db.LedgerError, match="needs a number"):
        graph.lineage(seeded, "austin")


def test_lineage_shows_unit_conversion(seeded):
    (reno,) = db.list_activities(seeded, period_id="2026-09", site_id="reno")
    assert "= 14.62 MWh as printed (MWh x 1000 = kWh)" in graph.lineage(seeded, reno["id"])["text"]


def test_impact_if_this_bill_is_wrong(seeded):
    calc = _with_calculation(seeded)
    new = _corrected_bill(seeded)["activities"][0]["id"]
    gap, _ = db.create_gap(seeded, kind="excerpt_mismatch", detail="x", created_by="cr-checker",
                           refs={"activity_id": AUSTIN_OCT})
    result = graph.impact(seeded, "ELB-AUS-2610")
    assert result["depends"] == {"activity": sorted([AUSTIN_OCT, new]), "calculation": [calc["id"]],
                                 "gap": [gap["id"]]}


def test_walks_do_not_leak_through_shared_hubs(seeded):
    out = graph.walk(seeded, "activity", AUSTIN_OCT, direction="out", max_depth=6)
    activities = [n["id"] for n in out["nodes"] if n["type"] == "activity"]
    assert activities == [AUSTIN_OCT]  # not every other Austin / October / Omar number
    assert {"site:austin", "period:2026-10", "person:omar", "room:cr-site-austin"} <= {n["key"] for n in out["nodes"]}
    lena = graph.walk(seeded, "person", "lena", direction="in", max_depth=2)
    assert {n["type"] for n in lena["nodes"]} == {"person", "doc", "activity", "site"}  # her docs, their numbers


def test_gap_refs_become_edges(seeded):
    unreadable = config.inbox_dir() / "cr-site-reno" / "photo.png"
    unreadable.parent.mkdir(parents=True)
    unreadable.write_bytes(b"\x89PNG nope")
    r = pipeline.ingest_file(seeded, unreadable, received_from="lena")
    (g,) = r["gaps"]
    rels = {(e["rel"], e["dst_type"]) for e in graph.edges(seeded, "gap", g["id"], "out")}
    assert {("about", "doc"), ("owned_by", "person"), ("raised_in", "room")} <= rels
    db.resolve_gap(seeded, g["id"], resolution="re-sent as PDF", resolved_by="lena")
    assert ("resolved_by", "person") in {(e["rel"], e["dst_type"]) for e in graph.edges(seeded, "gap", g["id"], "out")}


def test_upload_answers_gap_and_run_edges(seeded):
    from carbonroom.ingest import batch

    gap, _ = db.create_gap(seeded, kind="missing_doc", detail="Reno October bill", created_by="cr-checker",
                           period_id="2026-10", site_id="reno")
    bill = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    batch.run_batch(seeded, [bill], received_from="lena", meta={"gap_id": gap["id"]}, run_id="RUN-g", workers=1)
    doc = db.find_source_docs_by_ref(seeded, "ELB-RNO-2610")[0]
    rels = {(e["rel"], e["dst_id"]) for e in graph.edges(seeded, "doc", doc["id"], "out")}
    assert ("answers", gap["id"]) in rels and ("collected_in", "RUN-g") in rels


def test_period_graph_and_exports(seeded):
    _corrected_bill(seeded)
    g = graph.period_graph(seeded, "2026-10")
    keys = {n["key"] for n in g["nodes"]}
    assert all(f"activity:{a['id']}" in keys for a in db.list_activities(seeded, period_id="2026-10"))
    assert "period:2026-10" not in keys
    assert all(e["src"] in keys and e["dst"] in keys for e in g["edges"])
    mermaid = graph.to_mermaid(g)
    declared = set(re.findall(r"^  (n_\w+)\[", mermaid, flags=re.M))
    used = set(re.findall(r"(n_\w+) -->\|\w+\| (n_\w+)", mermaid))
    assert mermaid.startswith("flowchart LR") and all(a in declared and b in declared for a, b in used)
    data = json.loads(graph.to_json(g))
    assert data["type"] == "cr.graph.v1" and len(data["nodes"]) == len(g["nodes"])
    austin = graph.period_graph(seeded, "2026-10", site="austin")
    assert {n["type"] for n in austin["nodes"]} >= {"activity", "doc", "site"}
    assert "site:nimbus-cloud" not in {n["key"] for n in austin["nodes"]}
    assert graph.to_mermaid(austin) == graph.to_mermaid(graph.period_graph(seeded, "2026-10", site="austin"))


def test_views_are_recreated_when_their_version_changes(env, monkeypatch):
    conn = db.connect(env / "v.db")
    conn.execute("UPDATE schema_meta SET value = 'old' WHERE key = 'graph_version'")
    conn.execute("DROP VIEW ledger_nodes")
    conn.close()
    conn = db.connect(env / "v.db")  # migrate() notices the version and rebuilds both views
    assert conn.execute("SELECT value FROM schema_meta WHERE key='graph_version'").fetchone()[0] == db.GRAPH_VERSION
    assert conn.execute("SELECT COUNT(*) FROM ledger_nodes").fetchone()[0] == 0


def test_cli_trace_impact_graph(env, capsys, tmp_path):
    main(["seed"])
    capsys.readouterr()
    assert main(["ledger", "trace", AUSTIN_OCT]) == 0
    assert "proven by page 1, line 10" in capsys.readouterr().out
    assert main(["ledger", "trace", "ELB-AUS-2610"]) == 0
    assert "received_from: person:omar" in capsys.readouterr().out
    assert main(["ledger", "trace", AUSTIN_OCT, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["activity"]["id"] == AUSTIN_OCT
    assert main(["ledger", "impact", "ELB-AUS-2610"]) == 0
    assert "Depends on doc:" in capsys.readouterr().out
    assert main(["ledger", "graph", "--period", "2026-10", "--site", "reno"]) == 0
    assert capsys.readouterr().out.startswith("flowchart LR")
    out = tmp_path / "g.md"
    assert main(["ledger", "graph", "--period", "2026-10", "--out", str(out)]) == 0
    assert out.read_text().startswith("```mermaid\nflowchart LR")
    assert main(["ledger", "graph", "--period", "2026-10", "--format", "json", "--depth", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "cr.graph.v1"
    assert main(["ledger", "trace", "nothing-like-this"]) == 1
