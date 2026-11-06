"""Status, trace, audit and help handlers (SPEC-13)."""

from __future__ import annotations

from carbon_room.models import Actor
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


async def handle_status(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError


async def handle_trace(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError


async def handle_verify_audit(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError


async def handle_help(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError
