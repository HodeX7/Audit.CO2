"""Close Board room document."""

from __future__ import annotations

from carbon_room.room import messages
from carbon_room.room.ports import Context

BOARD_NAME: str = "close-board"


async def update_board(ctx: Context, close_id: str) -> bool:
    """Keep the close-board document in step with summary(); False when docs are unsupported."""
    s = await ctx.core.summary(close_id)
    text = messages.board(messages.month_label(messages.month_of(close_id)), s, ctx.display, ctx.room.link)
    return await ctx.room.upsert_doc("carbon-room", BOARD_NAME, text)
