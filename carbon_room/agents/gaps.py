"""Gap root posts for the close flow."""

from __future__ import annotations

from carbon_room.models import Finding
from carbon_room.room.ports import Context


def gap_number(gap_id: str) -> int:
    raise NotImplementedError


async def post_new_gaps(ctx: Context, close_id: str, findings: list[Finding]) -> list[str]:
    raise NotImplementedError
