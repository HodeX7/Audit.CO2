"""F4 room-attributed resolution and authorization."""

import pytest

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks import resolve
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger
from carbon_room.models import Actor, Finding, NeedsRoomEvent, NotAllowed, Option

LEAD = Actor("human", "lead", "Lead", "lead")
GUEST = Actor("human", "guest", "Guest", None)


def prepared(factor_db, close_id):
    collect.ingest(factor_db, close_id, CALCULATOR)
    calc_run.calculate(factor_db, close_id)
    check_run.check(factor_db, close_id)
    return {gap.rule: gap for gap in ledger.get_gaps(factor_db, close_id, status="OPEN")}


def test_pick_resolves_conflict_with_the_switch_message_and_supersedes_only_losers(factor_db, close_id):
    gap = prepared(factor_db, close_id)["R2"]
    choice = gap.options[0]
    with pytest.raises(NeedsRoomEvent):
        resolve.apply(factor_db, gap.gap_id, "pick", LEAD, None, choice.params)
    with pytest.raises(NotAllowed):
        resolve.apply(factor_db, gap.gap_id, "pick", GUEST, "msg-guest", choice.params)
    resolve.apply(factor_db, gap.gap_id, "pick", LEAD, "msg-pick", choice.params)
    chosen = choice.params["claim_id"]
    assert ledger.get_gap(factor_db, gap.gap_id, close_id).status == "RESOLVED"
    assert all(ledger.get_claim(factor_db, claim).superseded_by == chosen for claim in gap.claim_ids if claim != chosen)
    assert ledger.get_claim(factor_db, chosen).status == "VERIFIED"
    assert ledger.get_approvals(factor_db, close_id, subject_id=chosen)[0]["chat_message_id"] == "msg-pick"


def test_reject_keeps_claim_excluded_and_records_reason(factor_db, close_id):
    gap = prepared(factor_db, close_id)["R5"]
    claim_id = gap.claim_ids[0]
    resolve.apply(factor_db, gap.gap_id, "reject", LEAD, "msg-reject", {"reason": "bill needs correction"})
    assert ledger.get_gap(factor_db, gap.gap_id, close_id).resolution == {
        "outcome": "excluded",
        "reason": "bill needs correction",
    }
    assert ledger.get_claim(factor_db, claim_id).status != "VERIFIED"
    assert ledger.get_approvals(factor_db, close_id, subject_id=claim_id)[-1]["chat_message_id"] == "msg-reject"
    check_run.check(factor_db, close_id)
    assert ledger.get_claim(factor_db, claim_id).status != "VERIFIED"


def test_wrong_period_upload_does_not_commit_unmatched_evidence(factor_db, close_id, tmp_path):
    gap = prepared(factor_db, close_id)["R4"]
    factor_db.commit()
    wrong = tmp_path / "warehouse2_electricity_wrong_period.eml"
    wrong.write_text(
        "Subject: Electricity invoice\nFrom: synthetic@example.test\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "Site: warehouse-2\nPeriod: 2026-09-01 to 2026-09-30\nElectricity: 300 kWh\n",
        encoding="utf-8",
    )
    sources_before = len(ledger.get_sources(factor_db, close_id))
    claims_before = len(ledger.get_claims(factor_db, close_id))
    with pytest.raises(ValueError, match="no matching current-period claim"):
        resolve.apply(factor_db, gap.gap_id, "upload", LEAD, "msg-wrong-period", {"path": str(wrong)})
    assert len(ledger.get_sources(factor_db, close_id)) == sources_before
    assert len(ledger.get_claims(factor_db, close_id)) == claims_before
    assert ledger.get_gap(factor_db, gap.gap_id, close_id).status == "OPEN"


def test_same_gap_id_on_prior_close_does_not_block_latest_close(factor_db, close_id):
    prepared(factor_db, close_id)
    old = ledger.get_gap(factor_db, "G-1", close_id)
    latest = ledger.create_close(
        factor_db, "2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "msg-new-close"
    )
    new = ledger.upsert_gap(
        factor_db,
        latest,
        Finding(
            "new-finding",
            "R4",
            "PERIOD",
            [],
            "warehouse-2",
            "2026-10",
            "priya",
            "new gap",
            [],
            [Option("reject", "reject", "Reject")],
            2,
            True,
        ),
    )
    assert new.gap_id == "G-1"
    resolve.apply(factor_db, new.gap_id, "reject", LEAD, "msg-new-gap", {"reason": "exclude"})
    assert ledger.get_gap(factor_db, new.gap_id, latest).status == "RESOLVED"
    assert ledger.get_gap(factor_db, old.gap_id, close_id).status == "OPEN"
