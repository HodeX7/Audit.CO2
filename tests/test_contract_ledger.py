from __future__ import annotations

from decimal import Decimal
import sqlite3

import pytest

from carbon_room.ledger import ledger
from carbon_room.ledger.audit import verify_audit
from carbon_room.models import Actor, Calculation, Claim, Finding, NeedsRoomEvent, NotAllowed, Source


SYSTEM = Actor("system", "seed", "Seed")
HUMAN = Actor("human", "lead", "Lead", "lead")


def _close(db):
    return ledger.create_close(db, "2026-10", ["test-site"], "FS-test", SYSTEM, "msg-close")


def _claim(db, close_id):
    source = Source("SRC-0001", close_id, "test-site", "utility_pdf", "bill.pdf", "var/store/bill.pdf", "hash", 1,
                    "48,200 kWh", "2026-10-01", "2026-10-31", "OK", None)
    ledger.add_source(db, source, SYSTEM)
    return Claim("CL-0001", close_id, "test-site", "2026-10", "electricity_kwh", Decimal("48200.0"), "kWh", "2",
                 source.source_doc_id, "48,200 kWh", source.sha256, 1, None, None, "VERIFIED", "collector", "checker", None)


def test_close_versions_events_and_audit_chain(db):
    first = _close(db)
    second = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", SYSTEM, "msg-close-2")
    assert (first, second) == ("2026-10-v1", "2026-10-v2")
    ledger.set_phase(db, first, "COLLECTING", SYSTEM)
    assert verify_audit(db, first).ok


def test_claim_is_forced_unverified_and_status_guardrails_hold(db):
    close_id = _close(db)
    claim = _claim(db, close_id)
    claim_id = ledger.add_claim(db, claim, SYSTEM)
    assert ledger.get_claim(db, claim_id).status == "UNVERIFIED"
    with pytest.raises(NeedsRoomEvent):
        ledger.set_status(db, claim_id, "CONFLICTING", HUMAN, "needs evidence")
    with pytest.raises(NotAllowed):
        ledger.set_status(db, claim_id, "VERIFIED", HUMAN, "approval", "msg-approve")
    with pytest.raises(ValueError, match="MISSING"):
        ledger.set_status(db, claim_id, "MISSING", SYSTEM, "not a status")
    ledger.set_status(db, claim_id, "VERIFIED", Actor("agent", "watchdog", "Watchdog"), "all rules passed")
    assert ledger.get_claim(db, claim_id).status == "VERIFIED"


def test_claim_and_factor_boundaries_reject_invalid_or_mutable_inputs(db):
    close_id = _close(db)
    source = Source("SRC-boundary", close_id, "test-site", "utility_pdf", "bill.pdf", "var/store/bill.pdf", "boundary", 1,
                    "1 kWh", None, None, "OK", None)
    ledger.add_source(db, source, SYSTEM)
    invalid = Claim("CL-boundary", close_id, "test-site", "2026-10", "override_close", Decimal("1"), "kWh", "2",
                    source.source_doc_id, "1 kWh", source.sha256, 0, None, None, "UNVERIFIED", "collector", None, None)
    with pytest.raises(ValueError, match="unsupported claim activity"):
        ledger.add_claim(db, invalid, SYSTEM)
    invalid_value = Claim("CL-negative", close_id, "test-site", "2026-10", "electricity_kwh", Decimal("-1"), "kWh", "2",
                          source.source_doc_id, "-1 kWh", source.sha256, 0, None, None, "UNVERIFIED", "collector", None, None)
    with pytest.raises(ValueError, match="positive finite"):
        ledger.add_claim(db, invalid_value, SYSTEM)
    ledger.load_factors(db, [{
        "factor_id": "F-immutable", "source": "official", "version": "v1", "year": "2026",
        "activity": "electricity_kwh", "geography": "test", "value": Decimal("0.2"),
        "unit": "kgCO2e/kWh", "citation": "first",
    }])
    with pytest.raises(ValueError, match="immutable"):
        ledger.load_factors(db, [{
            "factor_id": "F-immutable", "source": "attacker", "version": "v9", "year": "2026",
            "activity": "electricity_kwh", "geography": "test", "value": Decimal("999"),
            "unit": "kgCO2e/kWh", "citation": "replaced",
        }])
    with pytest.raises(ValueError, match="positive finite"):
        ledger.load_factors(db, [{
            "factor_id": "F-negative", "source": "official", "version": "v1", "year": "2026",
            "activity": "electricity_kwh", "geography": "test", "value": Decimal("-1"),
            "unit": "kgCO2e/kWh", "citation": "invalid",
        }])


def test_ledger_rejects_unknown_contract_states_and_event_rewrites(db):
    close_id = _close(db)
    with pytest.raises(ValueError, match="unknown close phase"):
        ledger.set_phase(db, close_id, "DONE", SYSTEM)
    claim_id = ledger.add_claim(db, _claim(db, close_id), SYSTEM)
    with pytest.raises(ValueError, match="unknown claim status"):
        ledger.set_status(db, claim_id, "PENDING", SYSTEM, "not a contract status")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE events SET reason='rewritten' WHERE close_id=?", (close_id,))
    db.execute("DROP TRIGGER events_are_append_only_update")
    first_event = db.execute("SELECT event_id FROM events WHERE close_id=? ORDER BY event_id LIMIT 1", (close_id,)).fetchone()
    db.execute("UPDATE events SET reason='tampered' WHERE event_id=?", (first_event["event_id"],))
    audit = verify_audit(db, close_id)
    assert not audit.ok
    assert audit.first_bad_event_id == first_event["event_id"]


def test_source_tags_remain_unique_when_calculations_arrive_in_batches(db):
    close_id = _close(db)
    claim_id = ledger.add_claim(db, _claim(db, close_id), SYSTEM)
    ledger.load_factors(db, [{
        "factor_id": "F-1", "source": "factor-source", "version": "v1", "year": "2026",
        "activity": "electricity_kwh", "geography": "test", "value": Decimal("0.2"),
        "unit": "kgCO2e/kWh", "citation": "test",
    }])

    def calculation(calc_id):
        return Calculation(calc_id, claim_id, "F-1", "v1", Decimal("1"), "kWh", Decimal("0.2"),
                           "kgCO2e/kWh", Decimal("0.2"), "1 * 0.2", "location")

    first = ledger.add_calculation(db, calculation("CA-1"))
    second = ledger.add_calculation(db, calculation("CA-2"))
    assert ledger.assign_s_tags(db, close_id, 1, [first]) == {first: "S-001"}
    assert ledger.assign_s_tags(db, close_id, 1, [first, second]) == {first: "S-001", second: "S-002"}
    events_before_repeat = db.execute("SELECT COUNT(*) FROM events WHERE kind='s_tags_assigned'").fetchone()[0]
    assert ledger.assign_s_tags(db, close_id, 1, [first, second]) == {first: "S-001", second: "S-002"}
    assert db.execute("SELECT COUNT(*) FROM events WHERE kind='s_tags_assigned'").fetchone()[0] == events_before_repeat
    other_close = ledger.create_close(db, "2026-11", ["test-site"], "FS-test", SYSTEM, "msg-close-2")
    with pytest.raises(ValueError, match="does not belong"):
        ledger.assign_s_tags(db, other_close, 1, [first])


def test_gap_ids_restart_for_each_close_without_colliding_in_storage(db):
    first_close = _close(db)
    second_close = ledger.create_close(db, "2026-11", ["test-site"], "FS-test", SYSTEM, "msg-close-2")
    finding = Finding("F-test", "R1", "MISSING", ["CL-first"], "test-site", "2026-10", "lead", "Missing", [], [], 1, True)
    first_gap = ledger.upsert_gap(db, first_close, finding)
    second_gap = ledger.upsert_gap(
        db,
        second_close,
        Finding("F-test", "R1", "MISSING", ["CL-second"], "test-site", "2026-11", "lead", "Missing", [], [], 1, True),
    )
    assert (first_gap.gap_id, second_gap.gap_id) == ("G-1", "G-1")
    ledger.set_gap_thread(db, first_close, first_gap.gap_id, "thread-first")
    assert ledger.get_gap(db, first_gap.gap_id, first_close).thread_root_message_id == "thread-first"
    assert ledger.get_gap(db, second_gap.gap_id, second_close).thread_root_message_id is None
    with pytest.raises(ValueError, match="already linked"):
        ledger.set_gap_thread(db, second_close, second_gap.gap_id, "thread-first")
    ledger.resolve_gap(db, first_close, first_gap.gap_id, SYSTEM, "resolve-first", {"action": "upload"})
    assert ledger.get_gap(db, first_gap.gap_id, first_close).status == "RESOLVED"
    assert ledger.get_gap(db, second_gap.gap_id, second_close).status == "OPEN"
    edge_sources = {row["src"] for row in db.execute("SELECT src FROM edges WHERE rel='ABOUT'")}
    assert edge_sources == {f"{first_close}:G-1", f"{second_close}:G-1"}
