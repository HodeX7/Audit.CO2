"""Switch is load-bearing: no approval, no gap resolution and no publish without a chat message from the room.

The architecture's rule: every human action carries a `chat_message_id` and an actor from a Switch event. The
CLI can ingest, calculate and check (an unverified draft); it cannot approve, resolve or publish. The ledger
enforces this itself, so it holds even against raw SQL.
"""

from __future__ import annotations

import sqlite3

import pytest

from carbonroom.cli import main
from carbonroom.ledger import db


@pytest.fixture
def seeded(env):
    assert main(["seed"]) == 0
    conn = db.connect()
    yield conn
    conn.close()


def _drafted(conn, **kw):
    close = db.start_close(conn, "2026-10", actor="maya", factor_set="egrid-2024", **kw)
    for phase in ("COLLECTING", "CALCULATING", "CHECKING", "DRAFTED"):
        close = db.set_close_phase(conn, close["id"], phase, actor="cr-carbon-room")
    return close


@pytest.mark.parametrize("message_id", [None, "", "   "])
def test_an_approval_without_a_chat_message_is_refused(seeded, message_id):
    with pytest.raises(db.LedgerError, match="chat_message_id"):
        db.record_approval(seeded, period_id="2026-10", approver_handle="maya", decision="APPROVE",
                           chat_message_id=message_id)
    with pytest.raises(sqlite3.IntegrityError, match="chat_message_id"):  # raw SQL too
        seeded.execute("INSERT INTO approvals(id, period_id, approver_handle, decision, at, chat_message_id) "
                       "VALUES ('APR-x', '2026-10', 'maya', 'APPROVE', '2026-11-03T18:31:00Z', ?)", (message_id,))


def test_a_gap_is_closed_only_by_a_reply_in_the_room(seeded):
    gap, _ = db.create_gap(seeded, kind="missing_doc", detail="Reno October bill", created_by="cr-watchdog",
                           period_id="2026-10", site_id="reno", finding_id="F-R1-reno-2026-10")
    assert gap["finding_id"] == "F-R1-reno-2026-10"
    with pytest.raises(db.LedgerError, match="chat_message_id"):
        db.resolve_gap(seeded, gap["id"], resolution="uploaded", resolved_by="lena")
    with pytest.raises(sqlite3.IntegrityError, match="chat_message_id"):
        seeded.execute("UPDATE gaps SET status='RESOLVED', resolution='x', resolved_by='lena' WHERE id = ?",
                       (gap["id"],))
    done = db.resolve_gap(seeded, gap["id"], resolution="uploaded", resolved_by="lena", chat_message_id="mm-g1")
    assert (done["status"], done["resolved_message_id"]) == ("RESOLVED", "mm-g1")
    event = seeded.execute("SELECT * FROM events WHERE action = 'gap_resolved'").fetchone()
    assert event["chat_message_id"] == "mm-g1"  # and it's inside the audit chain's hash


def test_publish_needs_the_publishers_message_and_their_approve_from_the_room(seeded):
    close = _drafted(seeded, chat_message_id="mm-start")
    with pytest.raises(db.LedgerError, match="chat_message_id"):
        db.publish_close(seeded, close["id"], published_by="maya", chat_message_id=None)
    with pytest.raises(db.LedgerError, match="APPROVE from the room"):  # no approval yet
        db.publish_close(seeded, close["id"], published_by="maya", chat_message_id="mm-pub")
    db.record_approval(seeded, period_id="2026-10", approver_handle="grace", decision="APPROVE",
                       chat_message_id="mm-a1")
    with pytest.raises(db.LedgerError, match="APPROVE from the room"):  # someone else's approval doesn't count
        db.publish_close(seeded, close["id"], published_by="maya", chat_message_id="mm-pub")
    with pytest.raises(sqlite3.IntegrityError, match="publisher"):  # raw SQL can't skip the gate
        seeded.execute("UPDATE closes SET phase='PUBLISHED', published_by='maya', published_message_id='x' "
                       "WHERE id = ?", (close["id"],))
    db.record_approval(seeded, period_id="2026-10", approver_handle="maya", decision="APPROVE",
                       chat_message_id="mm-a2")
    published = db.publish_close(seeded, close["id"], published_by="maya", chat_message_id="mm-pub",
                                 report_sha256="ab" * 32)
    assert (published["phase"], published["published_message_id"]) == ("PUBLISHED", "mm-pub")
    assert db.get_period(seeded, "2026-10")["status"] == "CLOSED"
    with pytest.raises(sqlite3.IntegrityError, match="final"):
        seeded.execute("UPDATE closes SET report_sha256 = 'x' WHERE id = ?", (close["id"],))


def test_an_approval_from_before_this_version_started_does_not_count(seeded, monkeypatch):
    monkeypatch.setenv("CR_NOW", "2026-11-03T09:00:00Z")
    db.record_approval(seeded, period_id="2026-10", approver_handle="maya", decision="APPROVE",
                       chat_message_id="mm-old")
    monkeypatch.setenv("CR_NOW", "2026-11-04T09:00:00Z")
    close = _drafted(seeded)
    with pytest.raises(db.LedgerError, match="APPROVE from the room"):
        db.publish_close(seeded, close["id"], published_by="maya", chat_message_id="mm-pub")


def test_the_cli_can_draft_but_has_no_way_to_approve_resolve_or_publish(env, capsys):
    """The ledger CLI only reads and ingests; every human-gated write needs a message id it can't invent."""
    import argparse

    from carbonroom.cli import build_parser

    def names(parser, prefix=""):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    yield f"{prefix}{name}"
                    yield from names(sub, f"{prefix}{name} ")

    commands = list(names(build_parser()))
    assert "ledger verify" in commands  # the walk works
    for forbidden in ("approve", "resolve", "publish"):
        assert not [c for c in commands if forbidden in c], f"a CLI command can {forbidden}; only the room can"
