from __future__ import annotations

from pathlib import Path

import pytest

from carbon_room import collect, core
from carbon_room.ledger import ledger
from carbon_room.ledger.audit import verify_audit
from carbon_room.models import Actor

SYSTEM = Actor("system", "collector", "Collector")


def test_seed_ingest_creates_claims_and_is_idempotent(db):
    close_id = ledger.create_close(db, "2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-test", SYSTEM, "msg")
    db.commit()
    report = collect.ingest(db, close_id, SYSTEM)
    assert report.statement == "All 5 2026-10 sources collected."
    assert report.sources_seen == 9
    assert len(report.claims_created) == 9
    repeated = collect.ingest(db, close_id, SYSTEM)
    assert not repeated.claims_created
    assert not repeated.failed_sources


def test_seed_ingest_preserves_source_periods_and_diesel_scope(db):
    close_id = ledger.create_close(db, "2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-test", SYSTEM, "msg")
    db.commit()
    collect.ingest(db, close_id, SYSTEM)
    claims = db.execute(
        "SELECT activity, month, scope FROM claims WHERE close_id=? ORDER BY claim_id", (close_id,)
    ).fetchall()
    assert sum(claim["month"] == "2026-09" for claim in claims) == 5
    assert sum(claim["month"] == "2026-10" for claim in claims) == 4
    assert {claim["scope"] for claim in claims if claim["activity"] == "diesel_l"} == {"1"}
    assert verify_audit(db, close_id).ok


def test_uploaded_bill_uses_its_printed_period(db):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    db.commit()
    path = Path("data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf")
    claim_ids = collect.ingest_file(db, close_id, path, SYSTEM, month_from_period=True)
    assert ledger.get_claim(db, claim_ids[0]).month == "2026-10"


def test_human_upload_carries_its_room_message_id(db, monkeypatch):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    db.commit()
    monkeypatch.setattr(core, "connect", lambda: db)
    actor = Actor("human", "priya", "Priya", "site_manager")
    core.ingest_file(
        close_id, "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf", actor, "switch-msg", "warehouse-2"
    )
    events = db.execute(
        """SELECT kind, chat_message_id FROM events
           WHERE kind IN ('source_added', 'claim_added', 'room_file_ingested') ORDER BY event_id"""
    ).fetchall()
    assert [event["kind"] for event in events] == ["source_added", "claim_added", "room_file_ingested"]
    assert {event["chat_message_id"] for event in events} == {"switch-msg"}


def test_upload_rolls_back_source_claims_and_lease_when_room_event_fails(db, monkeypatch):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    db.commit()
    real_append = collect.append_event

    def fail_room_event(conn, close, actor, kind, **kwargs):
        if kind == "room_file_ingested":
            raise RuntimeError("room unavailable")
        return real_append(conn, close, actor, kind, **kwargs)

    monkeypatch.setattr(collect, "append_event", fail_room_event)
    with pytest.raises(RuntimeError, match="room unavailable"):
        collect.ingest_file(
            db,
            close_id,
            "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf",
            Actor("human", "priya", "Priya", "site_manager"),
            site="warehouse-2",
            month_from_period=True,
            chat_message_id="switch-msg",
        )
    assert db.execute("SELECT COUNT(*) FROM sources WHERE close_id=?", (close_id,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM claims WHERE close_id=?", (close_id,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM locks WHERE close_id=?", (close_id,)).fetchone()[0] == 0


def test_rejected_extraction_marks_the_source_failed_with_its_reason(db, monkeypatch):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    db.commit()
    monkeypatch.setattr(
        collect,
        "_candidates",
        lambda *_args: [
            {"activity": "electricity_kwh", "value": "10", "unit": "kWh", "excerpt": "invented", "page": 0}
        ],
    )
    claim_ids = collect.ingest_file(
        db,
        close_id,
        "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf",
        SYSTEM,
        site="warehouse-2",
        month_from_period=True,
    )
    source = ledger.get_sources(db, close_id)[0]
    assert claim_ids == []
    assert source.extract_status == "FAILED"
    assert source.extract_error == "excerpt is not verbatim source text"


def test_ingestion_can_identify_a_site_from_the_document_text(db, tmp_path):
    close_id = ledger.create_close(db, "2026-10", ["warehouse-2"], "FS-test", SYSTEM, "msg")
    db.commit()
    source_path = tmp_path / "invoice.txt"
    source_path.write_text("Warehouse-2 utility invoice\nUsage: 10 kWh", encoding="utf-8")
    claim_ids = collect.ingest_file(db, close_id, source_path, SYSTEM)
    assert ledger.get_claim(db, claim_ids[0]).site == "warehouse-2"
