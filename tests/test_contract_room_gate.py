from __future__ import annotations

import pytest

from carbon_room.ledger import ledger
from carbon_room.models import Actor, Finding, NeedsRoomEvent, NotAllowed, Option, Source


HUMAN = Actor("human", "lead", "Lead", "lead")
SYSTEM = Actor("system", "system", "System")


def test_every_p1_human_ledger_mutation_needs_a_room_message(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", SYSTEM, "start")
    source = Source("SRC-0001", close_id, "test-site", "utility_pdf", "bill.pdf", "var/store/bill.pdf", "hash", 1,
                    "text", None, None, "OK", None)
    ledger.add_source(db, source, SYSTEM)
    from carbon_room.models import Claim
    from decimal import Decimal
    claim_id = ledger.add_claim(db, Claim("CL-0001", close_id, "test-site", "2026-10", "electricity_kwh", Decimal("1"), "kWh", "2",
                                               source.source_doc_id, "1 kWh", source.sha256, 1, None, None, "UNVERIFIED", "collector", None, None), SYSTEM)
    finding = Finding("F-test", "R2", "CONFLICTING", [claim_id], "test-site", "2026-10", "lead", "Conflict", [], [Option("approve", "approve", "Approve")], 2, True)
    gap = ledger.upsert_gap(db, close_id, finding)
    with pytest.raises(NeedsRoomEvent):
        ledger.set_status(db, claim_id, "CONFLICTING", HUMAN, "human action")
    with pytest.raises(NeedsRoomEvent):
        ledger.set_factor(db, claim_id, "factor", "v1", HUMAN, "human action")
    with pytest.raises(NeedsRoomEvent):
        ledger.supersede(db, claim_id, None, HUMAN, "human action", None)
    with pytest.raises(NeedsRoomEvent):
        ledger.resolve_gap(db, close_id, gap.gap_id, HUMAN, None, {})
    with pytest.raises(NeedsRoomEvent):
        ledger.add_approval(db, close_id, "claim", claim_id, 2, HUMAN, "approve", "human action", None)
    with pytest.raises(NeedsRoomEvent):
        ledger.add_source(db, Source("SRC-human", close_id, "test-site", "utility_pdf", "human.pdf", "var/store/human.pdf", "human-hash", 1,
                                     "text", None, None, "OK", None), HUMAN)
    with pytest.raises(NeedsRoomEvent):
        ledger.add_claim(db, Claim("CL-human", close_id, "test-site", "2026-10", "electricity_kwh", Decimal("1"), "kWh", "2",
                                   source.source_doc_id, "1 kWh", source.sha256, 1, None, None, "UNVERIFIED", "collector", None, None), HUMAN)
    with pytest.raises(NotAllowed):
        ledger.set_phase(db, close_id, "COLLECTING", HUMAN)
