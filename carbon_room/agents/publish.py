"""Draft and publish handlers (SPEC-13)."""

from __future__ import annotations

from pathlib import Path

from carbon_room.models import Actor
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


async def handle_draft(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError


async def handle_publish(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError


async def list_outputs(out_dir: Path, close_id: str, version: int) -> list[str]:
    raise NotImplementedError
