"""Room message text to Intent. Pure: no I/O, no config, never raises."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

REASON_TRY_CLOSE: str = "Try: @carbon-room close October 2026"
REASON_TAG: str = "Which source tag? Copy one from the draft."


@dataclass(frozen=True)
class Intent:
    kind: str
    args: dict
    target_agent: str | None


def reason_unknown_month(word: str) -> str:
    return f"I don't know the month '{word}'."


def parse(body: str, *, in_thread: bool, today: date) -> Intent:
    raise NotImplementedError


def normalize_reply(text: str) -> tuple[str, str]:
    raise NotImplementedError
