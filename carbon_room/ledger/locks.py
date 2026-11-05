"""Short-lived ingestion locks keyed by close, source boundary and holder."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Iterator

from carbon_room.ledger.audit import append_event
from carbon_room.models import LockHeld


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@contextmanager
def claim_lock(conn: sqlite3.Connection, close_id: str, site: str, month: str, source_doc_id: str,
               holder: str) -> Iterator[None]:
    """Acquire a five-minute lock; stale holders are audibly replaced."""
    row = conn.execute("SELECT holder, acquired_at FROM locks WHERE close_id=? AND site=? AND month=? AND source_doc_id=?",
                       (close_id, site, month, source_doc_id)).fetchone()
    now = _now()
    if row:
        acquired = datetime.fromisoformat(row["acquired_at"].replace("Z", "+00:00"))
        if acquired > now - timedelta(minutes=5) and row["holder"] != holder:
            raise LockHeld(row["holder"])
        conn.execute("DELETE FROM locks WHERE close_id=? AND site=? AND month=? AND source_doc_id=?",
                     (close_id, site, month, source_doc_id))
        append_event(conn, close_id, holder, "stale_lock_taken", payload={"previous_holder": row["holder"]})
    conn.execute("INSERT INTO locks VALUES (?,?,?,?,?,?)", (close_id, site, month, source_doc_id, holder, now.isoformat().replace("+00:00", "Z")))
    try:
        yield
    finally:
        conn.execute("DELETE FROM locks WHERE close_id=? AND site=? AND month=? AND source_doc_id=? AND holder=?",
                     (close_id, site, month, source_doc_id, holder))
