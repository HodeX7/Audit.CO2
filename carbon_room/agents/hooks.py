"""Phase-end hook: board, then budgets."""

from __future__ import annotations

import logging

from carbon_room.agents.notices import check_budgets
from carbon_room.room.board import update_board
from carbon_room.room.ports import Context

log = logging.getLogger(__name__)


async def after_phase(ctx: Context, close_id: str) -> None:
    """Update the board, then check budgets. Never raises."""
    try:
        await update_board(ctx, close_id)
    except Exception:
        log.error("close board update failed for %s", close_id, exc_info=True)
    try:
        await check_budgets(ctx, close_id)
    except Exception:
        log.error("budget check failed for %s", close_id, exc_info=True)
