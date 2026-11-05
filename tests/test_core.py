"""The core API seam: P1 functions work, P2 slots plug in without editing core.py, and every step keeps the close's
phase in the ledger."""

from __future__ import annotations

import shutil

import pytest

from carbonroom import config, core
from carbonroom.cli import main
from carbonroom.ingest.hashing import sha256_file
from carbonroom.ledger import db


@pytest.fixture
def seeded(env, monkeypatch):
    assert main(["seed"]) == 0
    monkeypatch.setattr(core, "_IMPLS", {})
    monkeypatch.setattr(core, "_PLUGINS_LOADED", False)
    conn = db.connect()
    yield conn
    conn.close()


def _drop_reno_bill():
    target = config.inbox_dir() / "cr-site-reno" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(config.seed_dir() / "later" / target.name, target)
    return target


def test_start_close_is_idempotent_while_the_close_is_open(seeded):
    first = core.start_close("2026-10", None, "egrid-2024", "maya", "mm-1", conn=seeded)
    again = core.start_close("2026-10", ["austin"], "egrid-2025", "maya", "mm-2", conn=seeded)
    assert first == again == "CLOSE-2026-10-v1"
    assert db.get_close(seeded, first)["sites"] == ["austin", "nimbus-cloud", "reno"]  # the first lock holds


def test_ingest_reports_what_it_collected_all_unverified(seeded):
    close_id = core.start_close("2026-10", None, "egrid-2024", "maya", "mm-1", conn=seeded)
    report = core.ingest(close_id, conn=seeded)
    assert db.get_close(seeded, close_id)["phase"] == "COLLECTING"
    assert report["type"] == "cr.ingest-report.v1" and report["new_documents"] == 0  # the seed was already in
    assert report["claims_by_status"] == {"UNVERIFIED": 5}
    assert report["statement_complete"] is False
    assert report["expected_missing"] == [{"site": "reno", "category": "electricity", "owner": "lena"}]
    for doc in report["documents"]:
        stored = db.get_source_doc(seeded, doc["doc_id"])
        assert stored["sha256"] == doc["sha256"]
    logged = seeded.execute("SELECT * FROM events WHERE action = 'collection_reported'").fetchone()
    assert (logged["actor"], logged["ref"]) == ("cr-collector", close_id)

    _drop_reno_bill()
    report = core.ingest(close_id, conn=seeded)
    assert report["new_documents"] == 1 and report["statement_complete"] is True
    created = [db.get_activity(seeded, a) for a in report["claims_created"]]
    assert [(a["site_id"], a["category"], a["status"]) for a in created] == [("reno", "electricity", "UNVERIFIED")]
    assert "All expected 2026-10 sources collected" in report["summary_text"]


def test_room_helpers_resume_and_link_threads(seeded):
    close_id = core.start_close("2026-10", None, "egrid-2024", "maya", "mm-1", conn=seeded)
    gap, _ = db.create_gap(seeded, kind="missing_doc", detail="Reno October bill", created_by="cr-watchdog",
                           period_id="2026-10", site_id="reno", dedupe_key="missing:reno:2026-10")
    linked = core.record_gap_thread(gap["id"], "thread-22", "cr-watchdog", room="town-square", conn=seeded)
    assert linked["thread_id"] == "thread-22"
    assert core.gap_for_thread("thread-22", conn=seeded)["id"] == gap["id"]
    assert core.latest_close("2026-10", conn=seeded)["id"] == close_id
    assert core.resume_state(month="2026-10", conn=seeded)["close"]["id"] == close_id
    assert core.budget_usage(close_id, conn=seeded) == []


def test_ingest_file_records_the_human_room_message(seeded):
    close_id = core.start_close("2026-10", None, "egrid-2024", "maya", "mm-1", conn=seeded)
    path = _drop_reno_bill()
    claim_ids = core.ingest_file(close_id, path, "lena", "mm-upload-4", site="reno", conn=seeded)
    assert len(claim_ids) == 1
    event = seeded.execute("SELECT * FROM events WHERE action = 'room_file_ingested'").fetchone()
    assert (event["actor"], event["ref"], event["chat_message_id"]) == ("lena", close_id, "mm-upload-4")
    assert db.get_activity(seeded, claim_ids[0])["status"] == "UNVERIFIED"
    with pytest.raises(db.LedgerError, match="outside the locked boundary"):
        core.ingest_file(close_id, path, "lena", "mm-upload-5", site="not-a-site", conn=seeded)


def test_p2_slots_name_their_owner_until_plugged_in(seeded):
    close_id = core.start_close("2026-10", None, "egrid-2024", "maya", None, conn=seeded)
    with pytest.raises(NotImplementedError, match="P2"):
        core.calculate(close_id, conn=seeded)
    assert core.implemented() == {name: False for name in core.P2_FUNCTIONS}
    with pytest.raises(ValueError, match="not a P2 slot"):
        core.implements("ingest")


def test_a_whole_close_with_fake_p2_functions_keeps_the_phase(seeded):
    calls = []

    @core.implements("calculate")
    def calculate(close_id, conn):
        calls.append("calculate")
        return [{"activity_id": "x"}]

    @core.implements("check")
    def check(close_id, conn):
        calls.append("check")
        gap, _ = db.create_gap(conn, kind="missing_doc", detail="Reno October bill", created_by="cr-watchdog",
                               period_id="2026-10", site_id="reno", dedupe_key="missing:reno:2026-10")
        return [{"finding_id": "F-1", "gap_id": gap["id"]}]

    @core.implements("resolve")
    def resolve(gap_id, action, actor, chat_message_id, payload, conn):
        db.resolve_gap(conn, gap_id, resolution=action, resolved_by=actor, chat_message_id=chat_message_id)
        return []

    @core.implements("draft_report")
    def draft(close_id, conn):
        return {"report_sha256": "ab" * 32}

    @core.implements("publish")
    def publish(close_id, actor, chat_message_id, conn):
        return {"report_sha256": "ab" * 32, "version": 1}

    close_id = core.start_close("2026-10", None, "egrid-2024", "maya", "mm-1", conn=seeded)
    phase = lambda: db.get_close(seeded, close_id)["phase"]  # noqa: E731
    core.ingest(close_id, conn=seeded)
    core.calculate(close_id, conn=seeded)
    assert phase() == "CALCULATING"
    findings = core.check(close_id, conn=seeded)
    assert phase() == "AWAITING_HUMANS"
    with pytest.raises(db.LedgerError, match="chat_message_id"):
        core.resolve(findings[0]["gap_id"], "uploaded", "lena", "", conn=seeded)
    core.resolve(findings[0]["gap_id"], "uploaded the bill", "lena", "mm-7", conn=seeded)
    assert phase() == "RECHECKING"
    core.draft_report(close_id, conn=seeded)
    assert phase() == "DRAFTED"
    with pytest.raises(db.LedgerError, match="APPROVE from the room"):
        core.publish(close_id, "maya", "mm-9", conn=seeded)
    db.record_approval(seeded, period_id="2026-10", approver_handle="maya", decision="APPROVE", chat_message_id="mm-8")
    core.publish(close_id, "maya", "mm-9", conn=seeded)
    close = db.get_close(seeded, close_id)
    assert (close["phase"], close["published_message_id"], close["report_sha256"]) == ("PUBLISHED", "mm-9", "ab" * 32)
    assert calls == ["calculate", "check"]
    assert core.verify_audit(close_id, conn=seeded)["ok"]


def test_verify_audit_answers_for_the_room(seeded):
    close_id = core.start_close("2026-10", None, "egrid-2024", "maya", "mm-1", conn=seeded)
    check = core.verify_audit(close_id, conn=seeded)
    assert check["ok"] and check["summary_text"].startswith("Audit chain intact:")
    seeded.execute("DROP TRIGGER events_append_only")
    seeded.execute("UPDATE events SET actor = 'mallory' WHERE id = 3")
    check = core.verify_audit(close_id, conn=seeded)
    assert not check["ok"] and check["summary_text"].startswith("Audit chain BROKEN at event 3")


def test_the_cli_runs_the_p1_core_without_switch(seeded, capsys):
    assert main(["close", "start", "--month", "2026-10", "--factor-set", "egrid-2024", "--actor", "maya"]) == 0
    assert "CLOSE-2026-10-v1 OPEN" in capsys.readouterr().out
    assert main(["close", "ingest", "CLOSE-2026-10-v1"]) == 0
    assert "Statement: 1 expected 2026-10 source(s) still missing" in capsys.readouterr().out
    assert main(["close", "show", "CLOSE-2026-10-v1"]) == 0
    assert "COLLECTING" in capsys.readouterr().out
    assert main(["close", "verify-audit", "CLOSE-2026-10-v1"]) == 0
    assert sha256_file(config.db_path())  # the ledger file is there and readable
