"""Token budgets: a cap per agent per close (architecture lever "Budget per agent": warn at 80%, stop at 100%).

The tally lives in the ledger's audit chain, so it survives restarts and is the same for every process:
every model call made inside `scope(conn, close_id, agent)` appends an `llm_usage` event (actor = agent,
ref = close id, detail = task, model, tokens); crossing the warning line appends `budget_warning`, reaching the
cap appends `budget_exhausted`, and further calls raise llm.BudgetExceeded, which every caller already treats
as "no model": extraction falls back to the cache/rules, phrasing to the plain message.

    with budgets.scope(conn, "CLOSE-2026-10-v1", "cr-collector"):
        run_batch(conn, files)          # every extraction call is charged to cr-collector for this close
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from carbonroom import config, llm
from carbonroom.ledger import db


def cap_tokens() -> int:
    return int(config.env("CR_BUDGET_TOKENS", "200000"))


def warn_fraction() -> float:
    return float(config.env("CR_BUDGET_WARN", "0.8"))


def used(conn: sqlite3.Connection, close_id: str, agent: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(CAST(json_extract(detail_json, '$.tokens') AS INTEGER)), 0) AS n FROM events "
        "WHERE action = 'llm_usage' AND ref = ? AND actor = ?", (close_id, agent)).fetchone()
    return int(row["n"])


def for_close(conn: sqlite3.Connection, close_id: str, agent: str, *, cap: int | None = None) -> llm.Budget:
    """A Budget for `agent` on `close_id`, starting from what the ledger says was already spent."""
    path = conn.execute("PRAGMA database_list").fetchone()["file"]
    owner = threading.get_ident()
    local = threading.local()
    exhausted_logged = threading.Event()

    def record(tokens: int, info: dict[str, Any], warn: bool, exhausted: bool) -> None:
        # Worker threads can't use the caller's connection; each gets its own (SQLite serializes the writes).
        if threading.get_ident() == owner:
            c = conn
        else:
            c = getattr(local, "conn", None) or db.connect(path)
            local.conn = c
        db.log_event(c, agent, "llm_usage", close_id, {**info, "tokens": tokens})
        if warn:
            db.log_event(c, agent, "budget_warning", close_id, {"used": budget.used, "cap": budget.cap})
        if exhausted and not exhausted_logged.is_set():
            exhausted_logged.set()
            db.log_event(c, agent, "budget_exhausted", close_id, {"used": budget.used, "cap": budget.cap})

    budget = llm.Budget(agent, close_id, cap or cap_tokens(), used=used(conn, close_id, agent),
                        warn_at=warn_fraction(), record=record)
    return budget


@contextmanager
def scope(conn: sqlite3.Connection, close_id: str | None, agent: str, *,
          cap: int | None = None) -> Iterator[llm.Budget | None]:
    """Charge every model call in this block to `agent` on `close_id` (no close = no cap)."""
    budget = for_close(conn, close_id, agent, cap=cap) if close_id else None
    with llm.budget_scope(budget):
        yield budget


def report(conn: sqlite3.Connection, close_id: str) -> list[dict[str, Any]]:
    """Spend per agent for one close: tokens, calls, the cap, and whether it warned or ran out."""
    rows = conn.execute(
        "SELECT actor, COUNT(*) AS calls, SUM(CAST(json_extract(detail_json, '$.tokens') AS INTEGER)) AS tokens "
        "FROM events WHERE action = 'llm_usage' AND ref = ? GROUP BY actor ORDER BY actor", (close_id,)).fetchall()
    flags = {(r["actor"], r["action"]) for r in conn.execute(
        "SELECT DISTINCT actor, action FROM events WHERE ref = ? AND action IN ('budget_warning', 'budget_exhausted')",
        (close_id,))}
    cap = cap_tokens()
    return [{"agent": r["actor"], "calls": r["calls"], "tokens": int(r["tokens"] or 0), "cap": cap,
             "warned": (r["actor"], "budget_warning") in flags, "exhausted": (r["actor"], "budget_exhausted") in flags}
            for r in rows]
