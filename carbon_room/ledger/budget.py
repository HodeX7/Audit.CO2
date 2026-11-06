"""Persisted per-agent model-token budgets for a contract close."""

from __future__ import annotations

import sqlite3

from carbon_room.ledger.audit import append_event
from carbon_room.models import BudgetExceeded


def charge(
    conn: sqlite3.Connection, close_id: str, agent: str, tokens: int, *, limit: int = 200_000, warn_at: float = 0.8
) -> str:
    """Charge tokens before a call; warn once and stop before exceeding the limit."""
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise ValueError("token charge must be a non-negative integer")
    row = conn.execute(
        "SELECT tokens_used, limit_tokens FROM budgets WHERE close_id=? AND agent=?", (close_id, agent)
    ).fetchone()
    used, cap = (int(row["tokens_used"]), int(row["limit_tokens"])) if row else (0, limit)
    if used + tokens > cap:
        raise BudgetExceeded(f"{agent} exhausted its {cap}-token budget for {close_id}")
    updated = used + tokens
    conn.execute(
        "INSERT INTO budgets VALUES (?,?,?,?) "
        "ON CONFLICT(close_id,agent) DO UPDATE SET tokens_used=excluded.tokens_used",
        (close_id, agent, updated, cap),
    )
    state = "warn" if used < cap * warn_at <= updated else "ok"
    append_event(conn, close_id, agent, "budget_charged", payload={"tokens": tokens, "used": updated, "limit": cap})
    return state


def usage(conn: sqlite3.Connection, close_id: str, *, warn_at: float = 0.8) -> dict[str, dict[str, int | str]]:
    """Return room-ready budget state without performing a model call."""
    return {
        row["agent"]: {
            "used": row["tokens_used"],
            "limit": row["limit_tokens"],
            "state": "stopped"
            if row["tokens_used"] >= row["limit_tokens"]
            else "warn"
            if row["tokens_used"] >= row["limit_tokens"] * warn_at
            else "ok",
        }
        for row in conn.execute("SELECT * FROM budgets WHERE close_id=?", (close_id,))
    }
