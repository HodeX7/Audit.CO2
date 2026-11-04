"""A real SQLite-backed store implementing contracts/schema.sql exactly as
written, so the CLI (carbonroom/cli.py) has something real to run against
today rather than waiting on Person 1's ingestion pipeline.

This is a STAND-IN for Person 1's eventual `carbonroom/ledger/` db access
layer -- it reads and writes the exact same shared schema, so once their
real Collector/Consolidator is writing into this same SQLite file (or a
compatible one), every command below keeps working unmodified. Nothing
here is Person-2-only logic; it is pure plumbing around the shared tables.

One addition beyond contracts/schema.sql: a small `gap_activities` side
table (gap_id, activity_id). The shared `gaps` table (by team agreement)
has no column for "which activities does this gap concern" -- the CLI
needs that to resolve a conflict/stale/false-done gap by id later. This
table is clearly NOT part of the shared ledger contract; it is CLI-local
bookkeeping that Person 1's real db layer is free to replace however it
likes (e.g. folding it into `gaps.detail` as JSON instead).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "contracts" / "schema.sql"

_GAP_ACTIVITIES_TABLE = """
CREATE TABLE IF NOT EXISTS gap_activities (
  gap_id TEXT NOT NULL REFERENCES gaps(id),
  activity_id TEXT NOT NULL REFERENCES activities(id),
  PRIMARY KEY (gap_id, activity_id)
);
"""

# CLI-local, same as gap_activities above -- not part of the shared schema.
# Holds an LLM's translation of a loosely-phrased reply that has NOT been
# applied yet. A human must explicitly confirm before `resolve` acts on
# it -- this is what stops a model's comprehension error (e.g. picking
# "exclude" when the human meant "accept") from silently changing the
# ledger. See carbonroom/cli.py cmd_resolve.
_PENDING_RESOLUTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS pending_resolutions (
  gap_id TEXT PRIMARY KEY REFERENCES gaps(id),
  translated_text TEXT NOT NULL,
  proposed_by TEXT NOT NULL,
  original_reply TEXT NOT NULL,
  proposed_at TEXT NOT NULL
);
"""


def default_db_path() -> str:
    return os.environ.get("CR_DB_PATH", "./carbonroom.db")


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or default_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.executescript(_GAP_ACTIVITIES_TABLE)
    conn.executescript(_PENDING_RESOLUTIONS_TABLE)
    conn.commit()


def _dump_extra(value) -> str | None:
    return json.dumps(value) if value is not None else None


def _load_extra(value: str | None):
    return json.loads(value) if value else None


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "extra_json" in d:
        d["extra_json"] = _load_extra(d["extra_json"])
    return d


def fetch_all(conn: sqlite3.Connection, table: str, where: dict | None = None) -> list[dict]:
    where = where or {}
    clause = " AND ".join(f"{k} = ?" for k in where)
    sql = f"SELECT * FROM {table}" + (f" WHERE {clause}" if clause else "")
    rows = conn.execute(sql, tuple(where.values())).fetchall()
    return [_row_to_dict(r) for r in rows]


def fetch_one(conn: sqlite3.Connection, table: str, id_: str) -> dict | None:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()
    return _row_to_dict(row) if row else None


def upsert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    row = dict(row)
    if "extra_json" in row:
        row["extra_json"] = _dump_extra(row["extra_json"])
    # sqlite3 can't bind Decimal directly, and every REAL column would
    # coerce it to float on storage anyway -- do that conversion up front
    # so it's explicit. get_factors()/get_calculations() convert back to
    # Decimal on read, which is the only place exact arithmetic happens.
    for key, value in row.items():
        if isinstance(value, Decimal):
            row[key] = float(value)
    columns = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
    conn.execute(sql, tuple(row.values()))
    conn.commit()


def upsert_many(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    for row in rows:
        upsert(conn, table, row)


def update_fields(conn: sqlite3.Connection, table: str, id_: str, fields: dict) -> None:
    assignments = ", ".join(f"{k} = ?" for k in fields)
    sql = f"UPDATE {table} SET {assignments} WHERE id = ?"
    conn.execute(sql, (*fields.values(), id_))
    conn.commit()


# ---- Table-specific convenience readers --------------------------------

def get_sites(conn) -> list[dict]:
    return fetch_all(conn, "sites")


def get_periods(conn) -> list[dict]:
    return fetch_all(conn, "periods")


def get_period(conn, period_id: str) -> dict | None:
    return fetch_one(conn, "periods", period_id)


def get_activities(conn, period_id: str | None = None) -> list[dict]:
    return fetch_all(conn, "activities", {"period_id": period_id} if period_id else None)


def get_source_docs(conn) -> list[dict]:
    return fetch_all(conn, "source_docs")


def get_calculations(conn) -> list[dict]:
    """Same float-vs-Decimal normalization as get_factors(): the Reporter
    and Checker both do Decimal arithmetic on co2e_kg."""
    rows = fetch_all(conn, "calculations")
    for row in rows:
        row["co2e_kg"] = Decimal(str(row["co2e_kg"]))
    return rows


def get_factors(conn, set_version: str | None = None) -> list[dict]:
    """SQLite's REAL column affinity silently turns our stored Decimal
    strings back into floats on read. The Calculator does exact Decimal
    arithmetic and rejects a float outright (a loud TypeError, not a
    silent precision loss) -- so every factor is normalized back to
    Decimal here, via str(), before it leaves this module."""
    rows = fetch_all(conn, "emission_factors", {"set_version": set_version} if set_version else None)
    for row in rows:
        row["factor"] = Decimal(str(row["factor"]))
    return rows


def get_instruments(conn, period_id: str | None = None) -> list[dict]:
    return fetch_all(conn, "instruments", {"period_id": period_id} if period_id else None)


def get_gaps(conn, period_id: str | None = None) -> list[dict]:
    return fetch_all(conn, "gaps", {"period_id": period_id} if period_id else None)


def get_gap(conn, gap_id: str) -> dict | None:
    return fetch_one(conn, "gaps", gap_id)


def get_approvals(conn, period_id: str | None = None) -> list[dict]:
    return fetch_all(conn, "approvals", {"period_id": period_id} if period_id else None)


def get_gap_activity_ids(conn, gap_id: str) -> tuple[str, ...]:
    rows = conn.execute("SELECT activity_id FROM gap_activities WHERE gap_id = ?", (gap_id,)).fetchall()
    return tuple(r["activity_id"] for r in rows)


def set_gap_activity_ids(conn, gap_id: str, activity_ids: tuple[str, ...]) -> None:
    conn.execute("DELETE FROM gap_activities WHERE gap_id = ?", (gap_id,))
    conn.executemany(
        "INSERT INTO gap_activities (gap_id, activity_id) VALUES (?, ?)",
        [(gap_id, aid) for aid in activity_ids],
    )
    conn.commit()


def get_pending_resolution(conn, gap_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM pending_resolutions WHERE gap_id = ?", (gap_id,)).fetchone()
    return dict(row) if row else None


def set_pending_resolution(conn, gap_id: str, *, translated_text: str, proposed_by: str,
                            original_reply: str, proposed_at: str) -> None:
    upsert(conn, "pending_resolutions", {
        "gap_id": gap_id, "translated_text": translated_text, "proposed_by": proposed_by,
        "original_reply": original_reply, "proposed_at": proposed_at,
    })


def clear_pending_resolution(conn, gap_id: str) -> None:
    conn.execute("DELETE FROM pending_resolutions WHERE gap_id = ?", (gap_id,))
    conn.commit()


def update_activity_status(conn, activity_id: str, status: str) -> None:
    update_fields(conn, "activities", activity_id, {"status": status})


def update_instrument_quality(conn, instrument_id: str, quality_flags: str) -> None:
    update_fields(conn, "instruments", instrument_id, {"quality_flags": quality_flags})


def mark_period_closed(conn, period_id: str, approved_by: str, closed_at: str) -> None:
    update_fields(conn, "periods", period_id, {"status": "CLOSED", "approved_by": approved_by, "closed_at": closed_at})


# ---- Append-only event log (tamper-evident hash chain) ------------------

def _last_event_hash(conn) -> str | None:
    row = conn.execute("SELECT event_hash FROM events ORDER BY at DESC, id DESC LIMIT 1").fetchone()
    return row["event_hash"] if row else None


def append_event(conn, *, at: str, actor: str, action: str, ref: dict) -> dict:
    prev_hash = _last_event_hash(conn)
    event_id = f"evt-{uuid.uuid4().hex[:16]}"
    ref_json = json.dumps(ref, sort_keys=True, default=str)
    digest_input = f"{event_id}|{at}|{actor}|{action}|{ref_json}|{prev_hash or ''}"
    event_hash = hashlib.sha256(digest_input.encode()).hexdigest()
    row = {
        "id": event_id, "at": at, "actor": actor, "action": action, "ref": ref_json,
        "prev_event_hash": prev_hash, "event_hash": event_hash,
    }
    upsert(conn, "events", row)
    return row


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
