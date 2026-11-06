"""SQLite connection and schema initialisation for the contract ledger."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_PATH = Path("var/carbon_room.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str | Path = DEFAULT_PATH) -> sqlite3.Connection:
    """Open a contract ledger with SQLite's required safety pragmas enabled."""
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the frozen contract schema; safe to call repeatedly."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
