"""F7: every deliberate seed trap is visible before a human resolves it."""

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger


def test_all_seed_traps_are_actionable_and_block_verification(factor_db, close_id):
    ingestion = collect.ingest(factor_db, close_id, CALCULATOR)
    assert ingestion.statement == "All 5 2026-10 sources collected."
    calc_run.calculate(factor_db, close_id)
    findings = check_run.check(factor_db, close_id)
    gaps = {gap.rule: gap for gap in ledger.get_gaps(factor_db, close_id, status="OPEN")}
    assert set(gaps) == {"R2", "R3", "R4", "R5"}
    assert [option.key for option in gaps["R2"].options] == ["pick A", "pick B"]
    assert [option.key for option in gaps["R3"].options] == ["approve", "reject"]
    assert [option.key for option in gaps["R4"].options] == ["upload"]
    assert [option.key for option in gaps["R5"].options] == ["approve", "reject"]
    assert (gaps["R2"].kind, gaps["R2"].title.split()[0]) == ("CONFLICTING", "Conflicting")
    assert gaps["R3"].kind == "STALE" and "dc-eu-west" in gaps["R3"].title
    assert gaps["R4"].kind == "PERIOD" and "warehouse-2" in gaps["R4"].title
    assert gaps["R5"].kind == "VARIANCE" and "hq" in gaps["R5"].title
    period_finding = next(finding for finding in findings if finding.rule == "R4")
    assert "Expected current-month source is missing" in period_finding.evidence
    assert not any(finding.rule == "R1" for finding in findings)  # R1 evidence joins R4's single thread.
    assert all(
        ledger.get_claim(factor_db, claim_id).status != "VERIFIED"
        for gap in gaps.values()
        for claim_id in gap.claim_ids
    )
