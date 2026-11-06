"""Close Board room document."""

from __future__ import annotations

from carbon_room.room.ports import Context

BOARD_NAME: str = "close-board"


async def update_board(ctx: Context, close_id: str) -> bool:
    raise NotImplementedError
