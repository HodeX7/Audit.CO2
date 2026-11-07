"""Classify accepted Switch messages and dispatch them to room handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date

from carbon_room.agents import ask, orchestrator, publish, reports, resolution
from carbon_room.models import Actor
from carbon_room.room import errors, grammar, identity
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context

Handler = Callable[[Context, RoomEvent, Intent, Actor], Awaitable[None]]
HANDLERS: dict[str, Handler] = {
    "close.start": orchestrator.handle_close_start,
    "close.status": reports.handle_status,
    "close.resume": orchestrator.handle_resume,
    "close.publish": publish.handle_publish,
    "report.draft": publish.handle_draft,
    "report.trace": reports.handle_trace,
    "audit.verify": reports.handle_verify_audit,
    "help": reports.handle_help,
    "ask": ask.handle_ask,
    "gap.reply": resolution.handle_gap_reply,
    "gap.fallback": resolution.handle_gap_reply,
}


def classify(event: RoomEvent, *, today: date, single_agent: bool) -> Intent:
    intent = grammar.parse(event.body, in_thread=event.in_thread, today=today)
    if intent.kind == "ignore":
        return intent
    if intent.kind in ("gap.reply", "gap.fallback"):
        accepted = event.addressed or identity.is_known(event.sender)
    else:
        accepted = single_agent or (event.addressed and intent.target_agent == event.receiving_agent)
    return intent if accepted else Intent("ignore", {}, None)


async def handle(ctx: Context, event: RoomEvent, intent: Intent) -> None:
    actor = identity.actor_for(event.sender, event.sender_name)
    await HANDLERS[intent.kind](ctx, event, intent, actor)


async def on_error(ctx: Context, event: RoomEvent, intent: Intent, exc: BaseException) -> None:
    await ctx.room.post(intent.target_agent or "carbon-room",
                        errors.reply_for(exc, agent=intent.target_agent).text,
                        thread_id=event.thread_id or event.message_id)
