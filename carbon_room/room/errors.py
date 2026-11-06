"""Map exceptions to short, actionable replies (SPEC-04)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorReply:
    text: str
    error_id: str | None


def reply_for(exc: BaseException, *, agent: str | None = None,
              owner_name: str | None = None) -> ErrorReply:
    raise NotImplementedError("owner: P3, story P3-3.5")
