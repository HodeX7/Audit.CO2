from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from time import monotonic

import pytest

from carbon_room.ledger import connect, init_db, ledger
from carbon_room.ledger.locks import claim_lock
from carbon_room.models import Actor, LockHeld


def test_active_lock_rejects_another_worker_and_stale_lock_is_reclaimed(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg")
    db.commit()
    key = (close_id, "test-site", "2026-10", "SRC-0001")
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    db.execute("INSERT INTO locks VALUES (?,?,?,?,?,?)", (*key, "first-worker", now))
    db.commit()

    with pytest.raises(LockHeld):
        with claim_lock(db, *key, "second-worker"):
            pass

    stale = (datetime.now(UTC) - timedelta(minutes=6)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    db.execute(
        "UPDATE locks SET acquired_at=? WHERE close_id=? AND site=? AND month=? AND source_doc_id=?",
        (stale, *key),
    )
    db.commit()
    with claim_lock(db, *key, "second-worker"):
        holder = db.execute(
            "SELECT holder FROM locks WHERE close_id=? AND site=? AND month=? AND source_doc_id=?", key
        ).fetchone()["holder"]
        assert holder == "second-worker"
    assert db.execute("SELECT COUNT(*) FROM events WHERE kind='stale_lock_taken'").fetchone()[0] == 1


def test_claim_lock_requires_a_clean_transaction(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg")
    db.commit()
    db.execute("BEGIN")
    with pytest.raises(RuntimeError, match="without an active transaction"):
        with claim_lock(db, close_id, "test-site", "2026-10", "same-content", "worker"):
            pass
    db.rollback()


def test_two_connections_contending_during_a_source_write_report_the_lock_holder(tmp_path):
    database = tmp_path / "contended.db"
    setup = connect(database)
    init_db(setup)
    close_id = ledger.create_close(
        setup, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg"
    )
    setup.commit()
    setup.close()

    acquired = Event()
    release = Event()
    result = []

    def first_worker():
        conn = connect(database)
        try:
            with claim_lock(conn, close_id, "test-site", "2026-10", "same-content", "first-worker"):
                # This starts an actual SQLite writer transaction, matching the
                # source/claim writes performed by ingestion.
                conn.execute("INSERT INTO budgets VALUES (?,?,?,?)", (close_id, "first-worker", 1, 100))
                acquired.set()
                assert release.wait(timeout=5)
        finally:
            conn.close()

    def second_worker():
        assert acquired.wait(timeout=5)
        conn = connect(database)
        try:
            conn.execute("PRAGMA busy_timeout=100")
            started = monotonic()
            with pytest.raises(LockHeld) as error:
                with claim_lock(conn, close_id, "test-site", "2026-10", "same-content", "second-worker"):
                    pass
            result.append(str(error.value))
            assert monotonic() - started < 1
        finally:
            conn.close()

    first = Thread(target=first_worker)
    second = Thread(target=second_worker)
    first.start()
    second.start()
    assert acquired.wait(timeout=5)
    second.join(timeout=5)
    release.set()
    first.join(timeout=5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert result == ["first-worker"]
