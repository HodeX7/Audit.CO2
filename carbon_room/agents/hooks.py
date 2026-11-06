"""Phase-end hook: board, then budgets."""

from __future__ import annotations

from carbon_room.room.ports import Context


async def after_phase(ctx: Context, close_id: str) -> None:
    raise NotImplementedError
