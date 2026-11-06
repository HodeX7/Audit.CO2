"""Free-text ledger questions (SPEC-13)."""

from __future__ import annotations

from carbon_room.models import Actor
from carbon_room.room import messages
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


async def handle_ask(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    agent = intent.target_agent or "carbon-room"
    thread = event.thread_id or event.message_id
    close_id = await ctx.core.latest_close()
    if close_id is None:
        await ctx.room.post(agent, messages.no_close(), thread_id=thread)
        return
    answer = await ctx.core.explain(close_id, intent.args["question"], actor)
    await ctx.room.post(agent, answer, thread_id=thread)
