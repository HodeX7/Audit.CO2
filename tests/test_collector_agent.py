"""@collector: room event in, ops out; its "all collected" statement is checked, never trusted; it never marks
anything VERIFIED."""

from __future__ import annotations

import inspect
import io
import json
import shutil

import pytest

from carbonroom import config, core
from carbonroom.agents import collector
from carbonroom.cli import main
from carbonroom.ledger import db

RENO = "2026-10_reno_electricity_ELB-RNO-2610.pdf"


@pytest.fixture
def room(env, monkeypatch):
    """Seeded ledger with an open October close, as if Maya typed '@carbon-room close October'."""
    assert main(["seed"]) == 0
    monkeypatch.setattr(core, "_IMPLS", {})
    conn = db.connect()
    core.start_close("2026-10", None, "egrid-2024", "maya", "mm-close", conn=conn)
    yield conn
    conn.close()


def _event(text="", **kw):
    return {"type": "message", "message_id": "mm-100", "thread_id": None, "room": "october-close",
            "sender": "maya", "text": text, "addressed": True, **kw}


def test_silent_unless_addressed(room):
    assert collector.handle(_event("collect everything", addressed=False), conn=room) == []


def test_collect_posts_the_report_and_tells_the_orchestrator(room):
    ops = collector.handle({"type": "command", "command": "collect", "room": "october-close",
                            "message_id": "mm-101", "close_id": "CLOSE-2026-10-v1"}, conn=room)
    post, handoff = ops
    assert post["op"] == "post_message" and post["thread_id"] == "mm-101"
    assert "Statement: 1 expected 2026-10 source(s) still missing" in post["text"]
    assert "Reno Office electricity (@lena)" in post["text"]
    assert handoff["op"] == "send_targeted_message" and handoff["to"] == "@carbon-room"
    assert handoff["data"]["event"] == "collected" and handoff["data"]["statement_complete"] is False


def test_status_reports_without_collecting_again(room):
    collector.handle(_event("@collector collect October"), conn=room)
    runs_before = room.execute("SELECT COUNT(*) FROM events WHERE action = 'batch_started'").fetchone()[0]
    (op,) = collector.handle(_event("@collector status - what did you collect?"), conn=room)
    assert "CLOSE-2026-10-v1 (2026-10" in op["text"]
    assert room.execute("SELECT COUNT(*) FROM events WHERE action = 'batch_started'").fetchone()[0] == runs_before


def test_why_names_what_happened_to_a_document(room):
    (op,) = collector.handle(_event("@collector why didn't you consider INV-204B?"), conn=room)
    assert op["text"].startswith("INV-204B (2026-10_austin_diesel_INV-204B.pdf) reached the ledger")
    assert "austin 2026-10 diesel 550 gal UNVERIFIED" in op["text"]


def test_why_about_something_that_never_arrived_says_so_and_offers_what_exists(room):
    (op,) = collector.handle(_event("@collector why did you not consider the XYZ data center report?"), conn=room)
    assert op["text"].startswith('Nothing matching "xyz" has reached me')
    assert "NC-2610" in op["text"] and "cloud_compute 38,200 kWh UNVERIFIED" in op["text"]
    assert "Still expected for 2026-10: Reno Office electricity (@lena)" in op["text"]


def test_why_about_a_replaced_bill(room):
    later = config.seed_dir() / "later" / "2026-10_austin_electricity_ELB-AUS-2610-C.pdf"
    core.ingest("CLOSE-2026-10-v1", files=[later], received_from="omar", conn=room)
    text = collector.explain(room, "what happened to ELB-AUS-2610.pdf")["summary_text"]
    assert "it was replaced by ELB-AUS-2610-C" in text


def test_a_bill_dropped_in_a_gap_thread_is_ingested_and_handed_to_watchdog(room):
    gap, _ = db.create_gap(room, kind="missing_doc", detail="Reno October bill", created_by="cr-watchdog",
                           period_id="2026-10", site_id="reno")
    path = config.seed_dir() / "later" / RENO
    ops = collector.handle(_event("here it is", sender="lena", thread_id="mm-g1", gap_id=gap["id"],
                                  addressed=False, attachments=[{"name": RENO, "path": str(path)}]), conn=room)
    post, handoff = ops
    assert post["thread_id"] == "mm-g1"
    assert post["text"] == "Got ELB-RNO-2610: reno 2026-10 electricity 15,080 kWh UNVERIFIED."
    assert handoff["to"] == "@watchdog" and handoff["data"]["gap_ids"] == [gap["id"]]
    assert handoff["data"]["chat_message_id"] == "mm-100"
    doc = db.find_source_docs_by_ref(room, "ELB-RNO-2610")[0]
    assert (doc["received_from"], doc["meta"]["gap_id"], doc["meta"]["thread_id"]) == ("lena", gap["id"], "mm-g1")
    assert db.get_gap(room, gap["id"])["status"] == "OPEN"  # only a human (with the Watchdog) closes it

    (again,) = collector.handle(_event("sending again", sender="lena", thread_id="mm-g1", gap_id=gap["id"],
                                       attachments=[{"name": RENO, "path": str(path)}]), conn=room)[:1]
    assert "same file as ELB-RNO-2610" in again["text"]


def test_an_attachment_it_cannot_open_gets_the_inbox_fallback(room):
    (op,) = collector.handle(_event(attachments=[{"name": "warehouse.pdf"}]), conn=room)
    assert "Save the same file under data/inbox/october-close/" in op["text"]
    target = config.inbox_dir() / "october-close" / RENO
    target.parent.mkdir(parents=True)
    shutil.copy(config.seed_dir() / "later" / RENO, target)
    ops = collector.handle(_event(attachments=[{"name": RENO}]), conn=room)
    assert ops[0]["text"].startswith("Got ELB-RNO-2610")


def test_check_report_passes_an_honest_report_and_catches_a_false_one(room):
    report = core.ingest("CLOSE-2026-10-v1", conn=room)
    assert collector.check_report(room, report)["ok"]

    lie = dict(report, statement="All expected 2026-10 sources collected for 3 site(s)", statement_complete=True,
               expected_missing=[])
    problems = collector.check_report(room, lie)["problems"]
    assert any("does not match the ledger" in p for p in problems)

    hidden = dict(report, claims=report["claims"][1:])
    assert any("in scope when the report was made but not listed" in p
               for p in collector.check_report(room, hidden)["problems"])

    doc = db.get_source_doc(room, report["documents"][0]["doc_id"])
    from carbonroom.ingest import extract
    extract.resolve_doc_path(doc["path"]).write_bytes(b"tampered")
    assert any("no longer matches its SHA-256" in p for p in collector.check_report(room, report)["problems"])


def test_check_report_catches_the_collector_verifying_anything(room):
    report = core.ingest("CLOSE-2026-10-v1", conn=room)
    act = report["claims"][0]["id"]
    db.set_activity_status(room, act, "VERIFIED", actor=collector.ACTOR)  # what it must never do
    assert any("must never do that" in p for p in collector.check_report(room, report)["problems"])


def test_the_collector_never_marks_anything_verified(room):
    for event in (_event("@collector collect"), _event("@collector status"), _event("why not INV-204?"),
                  _event("hi", attachments=[{"name": RENO, "path": str(config.seed_dir() / "later" / RENO)}])):
        collector.handle(event, conn=room)
    assert db.list_activities(room, status="VERIFIED") == []
    source = inspect.getsource(collector)
    for forbidden in ("set_activity_status", "resolve_gap", "record_approval", "publish_close", "close_period",
                      "supersede_activity", "set_instrument_status"):
        assert forbidden not in source


def test_langgraph_node_and_cli_handle(room, monkeypatch, capsys):
    out = collector.collector_node({"close_id": "CLOSE-2026-10-v1"})
    assert out["ingest_reports"][0]["close_id"] == "CLOSE-2026-10-v1"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_event("@collector why not INV-204B?"))))
    assert main(["collector", "handle", "-"]) == 0
    ops = json.loads(capsys.readouterr().out)
    assert ops[0]["op"] == "post_message" and "INV-204B" in ops[0]["text"]
    assert main(["collector", "check-report", "--close", "CLOSE-2026-10-v1"]) == 0
