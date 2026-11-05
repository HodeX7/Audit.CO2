"""Short-lived ingestion locks keyed by close, source content boundary and holder."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Iterator

from carbon_room.ledger.audit import append_event
from carbon_room.models import LockHeld


_LEASE_TTL = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _row(conn: sqlite3.Connection, close_id: str, site: str, month: str, source_key: str):
    return conn.execute(
        "SELECT holder, acquired_at FROM locks WHERE close_id=? AND site=? AND month=? AND source_doc_id=?",
        (close_id, site, month, source_key),
    ).fetchone()


def _is_fresh(row: sqlite3.Row, now: datetime) -> bool:
    """Treat an unreadable timestamp as live rather than stealing its lease."""
    try:
        acquired = datetime.fromisoformat(row["acquired_at"].replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return True
    return acquired > now - _LEASE_TTL


def _active_holder(conn: sqlite3.Connection, close_id: str, site: str, month: str,
                   source_key: str, now: datetime) -> str | None:
    row = _row(conn, close_id, site, month, source_key)
    return str(row["holder"]) if row is not None and _is_fresh(row, now) else None


def _begin_immediate(conn: sqlite3.Connection) -> None:
    """Acquire SQLite's writer reservation without waiting behind an active lease.

    The caller first reads a committed lease.  A zero-wait acquisition then closes
    the tiny read-to-write race; a busy result is translated by ``claim_lock``.
    The connection's configured busy timeout is restored before returning.
    """
    timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
    conn.execute("PRAGMA busy_timeout=0")
    try:
        conn.execute("BEGIN IMMEDIATE")
    finally:
        conn.execute(f"PRAGMA busy_timeout={timeout}")


def _is_busy(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


def _contention(conn: sqlite3.Connection, close_id: str, site: str, month: str,
                source_key: str) -> LockHeld:
    """Return a retryable lock error, naming the committed holder when visible."""
    try:
        holder = _active_holder(conn, close_id, site, month, source_key, _now())
    except sqlite3.OperationalError:
        holder = None
    return LockHeld(holder or "another worker")


def _release(conn: sqlite3.Connection, close_id: str, site: str, month: str, source_key: str,
             holder: str) -> None:
    """Commit the work and removal of the published lease together."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "DELETE FROM locks WHERE close_id=? AND site=? AND month=? AND source_doc_id=? AND holder=?",
            (close_id, site, month, source_key, holder),
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


@contextmanager
def claim_lock(conn: sqlite3.Connection, close_id: str, site: str, month: str, source_key: str,
               holder: str) -> Iterator[None]:
    """Publish a five-minute lease for one content key and release it on exit.

    A lease is intentionally committed before yielding.  That makes it visible
    to a second SQLite connection even while the first worker is writing source
    rows.  Therefore this context manager owns its transaction boundary.
    """
    if conn.in_transaction:
        raise RuntimeError("claim_lock requires a connection without an active transaction")
    try:
        # Read before requesting SQLite's single writer slot.  In WAL mode this
        # remains available while the lease holder is writing its source rows.
        now = _now()
        if (current := _active_holder(conn, close_id, site, month, source_key, now)) is not None:
            raise LockHeld(current)

        _begin_immediate(conn)
        # Re-read after BEGIN IMMEDIATE to close the preflight/acquisition race.
        now = _now()
        row = _row(conn, close_id, site, month, source_key)
        if row is not None and _is_fresh(row, now):
            raise LockHeld(str(row["holder"]))
        expires_at = (now - _LEASE_TTL).isoformat().replace("+00:00", "Z")
        cursor = conn.execute(
            """INSERT INTO locks(close_id,site,month,source_doc_id,holder,acquired_at) VALUES (?,?,?,?,?,?)
               ON CONFLICT(close_id,site,month,source_doc_id) DO UPDATE SET
                 holder=excluded.holder, acquired_at=excluded.acquired_at
               WHERE locks.acquired_at <= ?""",
            (
                close_id, site, month, source_key, holder,
                now.isoformat().replace("+00:00", "Z"), expires_at,
            ),
        )
        if cursor.rowcount == 0:
            raise _contention(conn, close_id, site, month, source_key)
        if row is not None:
            append_event(conn, close_id, holder, "stale_lock_taken", payload={"previous_holder": row["holder"]})
        # Publish the reservation before source writes or model extraction.
        conn.commit()
    except sqlite3.OperationalError as error:
        if conn.in_transaction:
            conn.rollback()
        if _is_busy(error):
            raise _contention(conn, close_id, site, month, source_key) from error
        raise
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    try:
        yield
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        _release(conn, close_id, site, month, source_key, holder)
        raise
    else:
        _release(conn, close_id, site, month, source_key, holder)
