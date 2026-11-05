from __future__ import annotations

from decimal import Decimal

import pytest

from carbon_room.ledger import ledger
from carbon_room.ledger.audit import verify_audit
from carbon_room.models import Actor, Claim, NeedsRoomEvent, NotAllowed, Source


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
