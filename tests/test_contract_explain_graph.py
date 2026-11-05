from __future__ import annotations

from decimal import Decimal

from carbon_room import explain
from carbon_room.ledger import graph, ledger
from carbon_room.models import Actor, Calculation, Claim, Source


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
    assert result["missing"] == "calculation"


def test_explain_includes_verified_activity_and_latest_emissions(db):
    actor, close_id, claim_id = _claim(db)
    ledger.load_factors(db, [{
        "factor_id": "F-1", "source": "factor-source", "version": "v1", "year": "2026",
        "activity": "electricity_kwh", "geography": "test", "value": Decimal("0.2"),
        "unit": "kgCO2e/kWh", "citation": "test",
    }])
    ledger.set_factor(db, claim_id, "F-1", "v1", actor, "factor selected")
    ledger.add_calculation(db, Calculation(
        "CA-0001", claim_id, "F-1", "v1", Decimal("1"), "kWh", Decimal("0.2"),
        "kgCO2e/kWh", Decimal("0.2"), "1 * 0.2", "location",
    ))
    ledger.set_status(db, claim_id, "VERIFIED", actor, "all rules passed")
    answer = explain.answer(db, close_id, "What is hq electricity?", actor)
    assert "1 kWh" in answer
    assert "0.2 kgCO2e" in answer
