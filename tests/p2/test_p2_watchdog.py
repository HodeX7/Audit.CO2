"""F3 Watchdog acceptance against the synthetic close."""

import pytest

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger


def test_seed_detects_four_actionable_gaps_and_keeps_blocked_claims_unverified(factor_db, close_id):
    report = collect.ingest(factor_db, close_id, CALCULATOR)
    assert report.failed_sources == []
    assert len(report.claims_created) == 9
    calc_run.calculate(factor_db, close_id)
    findings = check_run.check(factor_db, close_id)
    assert {finding.rule for finding in findings} >= {"R2", "R3", "R4", "R5", "R6"}
    gaps = ledger.get_gaps(factor_db, close_id, status="OPEN")
    assert len(gaps) == 4, [(gap.rule, gap.kind, gap.title) for gap in gaps]
    assert {gap.rule for gap in gaps} == {"R2", "R3", "R4", "R5"}
    assert "could not be read" not in report.statement
    assert all(ledger.get_claim(factor_db, claim_id).status != "VERIFIED" for gap in gaps for claim_id in gap.claim_ids)
    before = factor_db.execute("SELECT COUNT(*) FROM events WHERE close_id=?", (close_id,)).fetchone()[0]
    check_run.check(factor_db, close_id)
    assert factor_db.execute("SELECT COUNT(*) FROM events WHERE close_id=?", (close_id,)).fetchone()[0] == before


def test_finding_ids_are_independent_of_input_claim_order():
    from carbon_room.checks.framework import make_finding

    common = ("R2", "CONFLICTING", "hq", "2026-10", "lead", "conflict", ["evidence"], [], 2, True)
    first = make_finding(common[0], common[1], ["CL-2", "CL-1"], *common[2:])
    second = make_finding(common[0], common[1], ["CL-1", "CL-2"], *common[2:])
    assert first.finding_id == second.finding_id
    assert first.claim_ids == ["CL-1", "CL-2"]


def test_missing_pue_calculation_errors_and_watchdog_identifies_missing_location(factor_db, close_id, add_claim):
    claim_id = add_claim(close_id, "dc-eu-west", "dc_it_kwh", "12000")
    with pytest.raises(ValueError, match="PUE"):
        calc_run.calculate(factor_db, close_id)
    findings = check_run.check(factor_db, close_id)
    assert any(item.rule == "R6" and item.blocking and claim_id in item.claim_ids for item in findings)
    assert ledger.get_claim(factor_db, claim_id).status != "VERIFIED"
