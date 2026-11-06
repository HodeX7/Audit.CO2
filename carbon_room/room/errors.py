"""Map exceptions to short, actionable replies (SPEC-04)."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from carbon_room.models import BudgetExceeded, LockHeld, NeedsRoomEvent, NotAllowed, NotFound

log = logging.getLogger("carbon_room.room.errors")


@dataclass(frozen=True)
class ErrorReply:
    text: str
    error_id: str | None


def _detail(exc: BaseException) -> str:
    try:
        text = str(exc).strip()
    except Exception:
        return ""
    first = text.splitlines()[0] if text else ""
    return first.strip().rstrip(".").strip()


def _generic(exc: BaseException, message: str | None = None) -> ErrorReply:
    error_id = secrets.token_hex(4)
    if message is None:
        message = f"unhandled error {error_id}: {type(exc).__name__}"
    else:
        message = message.format(error_id=error_id)
    log.error(message, exc_info=exc)
    return ErrorReply(
        f"Something went wrong on my side (error {error_id}). The ledger is unchanged.", error_id
    )


def reply_for(exc: BaseException, *, agent: str | None = None,
              owner_name: str | None = None) -> ErrorReply:
    try:
        if isinstance(exc, NeedsRoomEvent):
            return _generic(
                exc,
                "bug: a human action reached core without a chat message id (error {error_id})",
            )
        if isinstance(exc, NotAllowed):
            if owner_name:
                return ErrorReply(f"Only the Lead or the gap owner ({owner_name}) can do that.", None)
            return ErrorReply("Only the Lead can do that.", None)
        if isinstance(exc, LockHeld):
            return ErrorReply("@collector is still reading that source. Try again in a moment.", None)
        if isinstance(exc, BudgetExceeded):
            return ErrorReply(
                f"@{agent or 'carbon-room'} has hit its budget for this close and has stopped. "
                "The Lead can raise it in config.",
                None,
            )
        detail = _detail(exc)
        if isinstance(exc, NotFound):
            return ErrorReply(f"I can't find that: {detail}." if detail else "I can't find that.", None)
        if isinstance(exc, NotImplementedError):
            if detail:
                return ErrorReply(f"That step isn't built yet ({detail}). The ledger is unchanged.", None)
            return ErrorReply("That step isn't built yet. The ledger is unchanged.", None)
        if isinstance(exc, ValueError):
            return ErrorReply(f"I couldn't do that: {detail}." if detail else "I couldn't do that.", None)
        return _generic(exc)
    except Exception:  # never raise
        return ErrorReply("Something went wrong on my side. The ledger is unchanged.", None)
