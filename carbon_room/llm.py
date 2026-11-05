"""Model-agnostic JSON and phrasing boundary with replay-safe behavior."""

from __future__ import annotations

import json
from typing import Any


def complete_json(task: str, system: str, user: Any, agent: str, close_id: str) -> dict:
    """Call an injected model adapter; live provider wiring is configured, never hard-coded here."""
    raise RuntimeError(f"live model adapter is not configured for task {task!r}; use replay extraction or inject an adapter")


def phrase(question: str, facts: list[str], agent: str, close_id: str, *, scope: str = "this close",
           reason: str = "no VERIFIED ledger rows match", owner: str = "lead") -> str:
    """Never invoke a model when the truth set is empty."""
    if not facts:
        return f"UNKNOWN for {scope}, because {reason}, owned by {owner}"
    return "Verified ledger facts: " + "; ".join(facts)
