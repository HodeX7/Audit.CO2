"""Budget warn and stop notices."""

from __future__ import annotations

from carbon_room.room.ports import Context


async def warn_label() -> str:
    raise NotImplementedError


async def check_budgets(ctx: Context, close_id: str) -> list[str]:
    raise NotImplementedError
