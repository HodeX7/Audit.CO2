"""Contract identifier allocation from persisted ledger state."""

from __future__ import annotations

import sqlite3

_TABLES = {"SRC": ("sources", "source_doc_id"), "CL": ("claims", "claim_id"), "CA": ("calculations", "calc_id")}


def next_id(conn: sqlite3.Connection, prefix: str) -> str:
    """Reserve the next `PREFIX-0001` identifier in the caller's write transaction."""
    try:
        table, column = _TABLES[prefix]
    except KeyError as exc:
        raise ValueError(f"unsupported identifier prefix: {prefix}") from exc
    if not conn.in_transaction:
        # Allocation based on MAX(id) is safe only while the following INSERT is
        # protected by the same writer reservation. Callers commit or roll back
        # after persisting the object that owns this identifier.
        conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} GLOB ? ORDER BY {column} DESC LIMIT 1", (f"{prefix}-*",)
    ).fetchone()
    number = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}-{number:04d}"
