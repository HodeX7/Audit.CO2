from __future__ import annotations

from decimal import Decimal

from carbon_room import explain
from carbon_room.ledger import graph, ledger
from carbon_room.models import Actor, Claim, Source


def _claim(db):
    actor = Actor("system", "system", "System")
    close_id = ledger.create_close(db, "2026-10", ["hq"], "FS-test", actor, "start")
    source = Source("SRC-0001", close_id, "hq", "utility_pdf", "bill.pdf", "var/store/bill.pdf", "hash", 1, "Usage: 1 kWh", None, None, "OK", None)
    ledger.add_source(db, source, actor)
    claim_id = ledger.add_claim(db, Claim("CL-0001", close_id, "hq", "2026-10", "electricity_kwh", Decimal("1"), "kWh", "2", source.source_doc_id, "Usage: 1 kWh", source.sha256, 1, None, None, "UNVERIFIED", "collector", None, None), actor)
    return actor, close_id, claim_id


def test_explain_says_unknown_when_only_unverified_rows_exist(db):
    actor, close_id, _ = _claim(db)
    assert "UNKNOWN" in explain.answer(db, close_id, "What is hq electricity?", actor)


def test_graph_chain_names_missing_calculation(db):
    _, _, claim_id = _claim(db)
    result = graph.chain(db, claim_id)
    assert not result["complete"]
    assert result["missing"] == "factor"
