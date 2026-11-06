"""Draft and publish handlers (SPEC-13)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from carbon_room.models import Actor, NotAllowed
from carbon_room.room import errors, messages
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


async def handle_draft(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    close_id = await ctx.core.latest_close()
    if close_id is None:
        await ctx.room.post("reporter", messages.no_close(), thread_id=event.thread_id or event.message_id)
        return
    report = await ctx.core.draft_report(close_id)
    text = messages.draft(report, messages.month_label(messages.month_of(close_id)))
    await ctx.room.post("reporter", text)
    await ctx.on_phase_end(close_id)


async def handle_publish(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    thread = event.thread_id or event.message_id

    async def say(text: str) -> None:
        await ctx.room.post("carbon-room", text, thread_id=thread)

    if actor.role is None:
        await say(errors.reply_for(NotAllowed("guest")).text)
        return
    close_id = await ctx.core.latest_close()
    if close_id is None:
        await say(messages.no_close())
        return
    phase, _ = await ctx.core.resume_state(close_id)
    if phase != "DRAFTED":
        await ctx.core.draft_report(close_id)
    try:
        report = await ctx.core.publish(close_id, actor, event.message_id)
    except NotAllowed as exc:
        await say(errors.reply_for(exc).text)
        return
    paths = await list_outputs(ctx.out_dir, close_id, report.version)
    await ctx.room.post("carbon-room", messages.published(report, ctx.display(actor.id), paths))
    await ctx.on_phase_end(close_id)


def _list_outputs(out_dir: Path, close_id: str, version: int) -> list[str]:
    base = out_dir / messages.month_of(close_id) / f"v{version}"
    if not base.is_dir():
        return []
    return sorted(p.as_posix() for p in base.rglob("*") if p.is_file())


async def list_outputs(out_dir: Path, close_id: str, version: int) -> list[str]:
    return await asyncio.to_thread(_list_outputs, out_dir, close_id, version)
