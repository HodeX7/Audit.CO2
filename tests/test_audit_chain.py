"""The audit chain: every event is hashed onto the one before, so a changed past is detectable."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from carbonroom.cli import main
from carbonroom.ledger import db


def _drop_guards(conn):
    """What an attacker with raw SQL would do first."""
    conn.execute("DROP TRIGGER events_append_only")
    conn.execute("DROP TRIGGER no_delete_events")


def test_every_event_is_chained_and_verifies(conn):
    for i in range(5):
        db.log_event(conn, "cr-test", "step", f"R-{i}", {"i": i})
    rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
    assert rows[0]["prev_event_hash"] is None
    for before, row in zip(rows, rows[1:]):
        assert row["prev_event_hash"] == before["event_hash"]
    last = rows[-1]
    assert last["event_hash"] == db.event_hash(last["prev_event_hash"], last["at"], last["actor"], last["action"],
                                               last["ref"], last["chat_message_id"], last["detail_json"])
    result = db.verify_audit_chain(conn)
    assert result == {"ok": True, "events": len(rows), "broken": 0, "problems": [],
                      "head": {"id": last["id"], "event_hash": last["event_hash"]}}
    assert db.audit_head(conn)["event_hash"] == last["event_hash"]


def test_the_chat_message_id_is_part_of_the_link(conn):
    db.log_event(conn, "maya", "gap_resolved", "GAP-001", {"resolution": "use INV-204B"}, chat_message_id="mm-81f2")
    db.log_event(conn, "cr-collector", "doc_received", "DOC-1")
    row = conn.execute("SELECT * FROM events WHERE ref = 'GAP-001'").fetchone()
    assert row["chat_message_id"] == "mm-81f2"
    _drop_guards(conn)
    conn.execute("UPDATE events SET chat_message_id = 'mm-forged' WHERE id = ?", (row["id"],))
    assert db.verify_audit_chain(conn)["problems"][0]["id"] == row["id"]


def test_editing_a_past_event_is_found_where_it_happened(conn):
    for i in range(6):
        db.log_event(conn, "cr-test", "step", f"R-{i}", {"qty": "500"})
    _drop_guards(conn)
    target = conn.execute("SELECT id FROM events WHERE ref = 'R-2'").fetchone()["id"]
    conn.execute("UPDATE events SET detail_json = '{\"qty\":\"550\"}' WHERE id = ?", (target,))
    result = db.verify_audit_chain(conn)
    assert not result["ok"]
    assert result["problems"][0] == {"id": target, "problem": "event_hash does not match the event's content"}


def test_rehashing_after_an_edit_still_breaks_the_next_link(conn):
    for i in range(4):
        db.log_event(conn, "cr-test", "step", f"R-{i}")
    _drop_guards(conn)
    row = conn.execute("SELECT * FROM events WHERE ref = 'R-1'").fetchone()
    forged = db.event_hash(row["prev_event_hash"], row["at"], "omar", row["action"], row["ref"],
                           row["chat_message_id"], row["detail_json"])
    conn.execute("UPDATE events SET actor = 'omar', event_hash = ? WHERE id = ?", (forged, row["id"]))
    problems = db.verify_audit_chain(conn)["problems"]
    assert problems[0]["id"] == row["id"] + 1  # the next event still points at the old hash
    assert "prev_event_hash" in problems[0]["problem"]


def test_removing_an_event_breaks_the_chain(conn):
    for i in range(4):
        db.log_event(conn, "cr-test", "step", f"R-{i}")
    _drop_guards(conn)
    conn.execute("DELETE FROM events WHERE ref = 'R-1'")
    assert not db.verify_audit_chain(conn)["ok"]


@pytest.mark.parametrize("prev, link", [
    (None, None),                      # no hash at all
    ("same-as-newest", "f" * 64),      # chains correctly but the hash is made up -> verify finds it
    ("0" * 64, "f" * 64),              # forks off a hash that isn't the newest
])
def test_raw_inserts_must_extend_the_newest_event(conn, prev, link):
    db.log_event(conn, "cr-test", "first")
    newest = db.audit_head(conn)["event_hash"]
    prev = newest if prev == "same-as-newest" else prev
    sql = ("INSERT INTO events(at, actor, action, ref, detail_json, prev_event_hash, event_hash) "
           "VALUES ('2026-11-03T18:31:00Z', 'x', 'y', NULL, '{}', ?, ?)")
    if prev == newest:
        conn.execute(sql, (prev, link))
        assert not db.verify_audit_chain(conn)["ok"]
    else:
        with pytest.raises(sqlite3.IntegrityError, match="hash chain"):
            conn.execute(sql, (prev, link))


def test_agents_writing_at_once_never_fork_the_chain(env):
    db.connect().close()

    def agent(name):
        c = db.connect()
        for i in range(40):
            db.log_event(c, f"cr-{name}", "step", f"{name}-{i}")
        c.close()

    threads = [threading.Thread(target=agent, args=(n,)) for n in ("collector", "watchdog", "reporter", "chaser")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    conn = db.connect()
    result = db.verify_audit_chain(conn)
    assert result["ok"] and result["events"] == 160
    assert conn.execute("SELECT count(DISTINCT prev_event_hash) FROM events").fetchone()[0] == 159  # + one NULL


def test_an_older_ledger_gets_its_events_hashed_once(conn):
    for i in range(3):
        db.log_event(conn, "cr-test", "step", f"R-{i}")
    # Make it look like a ledger from before the chain: same events, empty hash columns.
    conn.execute("DROP TRIGGER events_append_only")
    conn.execute("UPDATE events SET prev_event_hash = NULL, event_hash = NULL")
    conn.executescript("CREATE TRIGGER events_append_only BEFORE UPDATE ON events "
                       "BEGIN SELECT RAISE(ABORT, 'carbonroom: events are append-only'); END;")
    applied = db.migrate(conn)
    assert "audit chain: hashed 3 older event(s)" in applied
    assert db.verify_audit_chain(conn)["ok"]
    last = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 1").fetchone()
    assert (last["action"], last["actor"]) == ("audit_chain_backfilled", "cr-ledger")
    assert not any("audit chain" in step for step in db.migrate(conn))  # only once
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):  # the guard is back
        conn.execute("UPDATE events SET actor = 'x' WHERE id = 1")


def test_ledger_verify_reports_the_chain(env, capsys):
    assert main(["seed"]) == 0
    capsys.readouterr()
    assert main(["ledger", "verify"]) == 0
    out = capsys.readouterr().out
    assert "OK   audit chain:" in out and "head #" in out
    conn = db.connect()
    _drop_guards(conn)
    conn.execute("UPDATE events SET actor = 'someone-else' WHERE id = 2")
    conn.close()
    assert main(["ledger", "verify"]) == 1
    out = capsys.readouterr().out
    assert "FAIL event 2: event_hash does not match the event's content" in out
    assert "FAIL audit chain:" in out
