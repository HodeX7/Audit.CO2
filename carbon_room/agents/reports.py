"""Status, trace, audit and help handlers (SPEC-13)."""

from __future__ import annotations

from carbon_room.models import Actor, NotFound
from carbon_room.room import messages
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


def _thread(event: RoomEvent) -> str:
    return event.thread_id or event.message_id


async def handle_status(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    thread = _thread(event)
    close_id = await ctx.core.latest_close()
    if close_id is None:
        await ctx.room.post("carbon-room", messages.no_close(), thread_id=thread)
        return
    summary = await ctx.core.summary(close_id)
    label = messages.month_label(messages.month_of(close_id))
    await ctx.room.post("carbon-room", messages.summary_post(label, summary, ctx.display), thread_id=thread)


async def handle_trace(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    thread = _thread(event)
    close_id = await ctx.core.latest_close()
    if close_id is None:
        await ctx.room.post("reporter", messages.no_close(), thread_id=thread)
        return
    wanted = intent.args["tag"]
    try:
        tag = await ctx.core.trace(close_id, wanted)
    except NotFound:
        await ctx.room.post("reporter", messages.tag_not_found(wanted), thread_id=thread)
        return
    link = ctx.room.link(tag.chat_message_id) if tag.chat_message_id else None
    await ctx.room.post("reporter", messages.trace_card(tag, link), thread_id=thread)


async def handle_verify_audit(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    thread = _thread(event)
    close_id = await ctx.core.latest_close()
    if close_id is None:
        await ctx.room.post("reporter", messages.no_close(), thread_id=thread)
        return
    check = await ctx.core.verify_audit(close_id)
    await ctx.room.post("reporter", messages.audit_result(check), thread_id=thread)


async def handle_help(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    await ctx.room.post(intent.target_agent or "carbon-room", messages.help_text(intent.args.get("reason")),
                        thread_id=_thread(event))
