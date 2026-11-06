"""Free-text ledger questions (SPEC-13)."""

from __future__ import annotations

from carbon_room.models import Actor
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


async def handle_ask(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError
