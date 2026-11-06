"""Contract identifier allocation from persisted ledger state."""

from __future__ import annotations

import sqlite3

_TABLES = {"SRC": ("sources", "source_doc_id"), "CL": ("claims", "claim_id"), "CA": ("calculations", "calc_id")}


def next_id(conn: sqlite3.Connection, prefix: str) -> str:
    """Return the next durable `PREFIX-0001` identifier for a contract table."""
    try:
        table, column = _TABLES[prefix]
    except KeyError as exc:
        raise ValueError(f"unsupported identifier prefix: {prefix}") from exc
    row = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} GLOB ? ORDER BY {column} DESC LIMIT 1", (f"{prefix}-*",)
    ).fetchone()
    number = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}-{number:04d}"
