"""Offline F7 seed flow through all four actionable Watchdog threads."""

from pathlib import Path

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks import resolve
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger
from carbon_room.models import Actor
from carbon_room.report import summary

LEAD = Actor("human", "lead", "Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")


def test_scripted_seed_resolutions_change_totals_and_preserve_audit(factor_db, close_id):
    collect.ingest(factor_db, close_id, CALCULATOR)
    calc_run.calculate(factor_db, close_id)
    check_run.check(factor_db, close_id)
    before = summary.build(factor_db, close_id)
    assert len(before.open_gaps) == 4
    assert before.coverage_pct < 100

    def gap(rule):
        return next(item for item in ledger.get_gaps(factor_db, close_id, status="OPEN") if item.rule == rule)

    conflict = gap("R2")
    first = conflict.options[0]
    resolve.apply(factor_db, conflict.gap_id, first.action, LEAD, "msg-pick", first.params)

    stale = gap("R3")
    approve_stale = next(item for item in stale.options if item.action == "approve")
    resolve.apply(factor_db, stale.gap_id, "approve", LEAD, "msg-stale", approve_stale.params)

    variance = gap("R5")
    resolve.apply(factor_db, variance.gap_id, "approve", LEAD, "msg-variance", {})

    factor_db.commit()  # P1's upload lock starts a separate writer transaction.
    period = gap("R4")
    upload = Path("data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf")
    resolve.apply(factor_db, period.gap_id, "upload", PRIYA, "msg-upload", {"path": str(upload)})

    after = summary.build(factor_db, close_id)
    assert after.verified_kgco2e > before.verified_kgco2e
    assert after.sources_verified == after.sources_expected == 4, [
        (claim.site, claim.activity, claim.month, claim.status) for claim in ledger.get_claims(factor_db, close_id)
    ]
    assert after.open_gaps == []
    assert after.coverage_pct == 100
    from carbon_room.ledger.audit import verify_audit

    assert verify_audit(factor_db, close_id).ok
