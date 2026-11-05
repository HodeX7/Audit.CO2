from __future__ import annotations

from pathlib import Path

from carbon_room import collect, core
from carbon_room.ledger import ledger
from carbon_room.models import Actor


SYSTEM = Actor("system", "collector", "Collector")


def test_seed_ingest_creates_claims_and_is_idempotent(db):
    close_id = ledger.create_close(db, "2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-test", SYSTEM, "msg")
    report = collect.ingest(db, close_id, SYSTEM)
    assert report.statement == "All 5 2026-10 sources collected."
    assert report.sources_seen == 9
    assert len(report.claims_created) == 9
    repeated = collect.ingest(db, close_id, SYSTEM)
    assert not repeated.claims_created


def test_uploaded_bill_uses_its_printed_period(db):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    path = Path("data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf")
    claim_ids = collect.ingest_file(db, close_id, path, SYSTEM, month_from_period=True)
    assert ledger.get_claim(db, claim_ids[0]).month == "2026-10"


def test_human_upload_carries_its_room_message_id(db, monkeypatch):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    monkeypatch.setattr(core, "connect", lambda: db)
    actor = Actor("human", "priya", "Priya", "site_manager")
    core.ingest_file(close_id, "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf", actor, "switch-msg", "warehouse-2")
    event = db.execute("SELECT chat_message_id FROM events WHERE kind='room_file_ingested'").fetchone()
    assert event["chat_message_id"] == "switch-msg"
