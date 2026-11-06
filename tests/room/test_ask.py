# ruff: noqa: E501
"""Free-text ledger questions (SPEC-13 section 6)."""

from __future__ import annotations

import asyncio

from fakes.fake_core import FakeCore

from carbon_room.agents.ask import handle_ask
from carbon_room.agents.orchestrator import handle_close_start
from carbon_room.models import Actor
from carbon_room.room import messages
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
CID = "2026-10-v1"
QUESTION = "what is Warehouse-2 October electricity?"
G1_PARAMS = {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}


def make_event(body, *, message_id, thread_id=None, attachments=(), receiving_agent="collector"):
    return RoomEvent("message", "!r:test", message_id, thread_id, "@x:test", "x", body,
                     tuple(attachments), True, 0, receiving_agent, 1)


def run_close(ctx, message_id="h-1"):
    event = make_event("@carbon-room close October", message_id=message_id, receiving_agent="carbon-room")
    return handle_close_start(ctx, event, Intent("close.start", {"month": "2026-10"}, "carbon-room"), LEAD)


def ask(ctx, *, message_id="h-7", thread_id=None):
    event = make_event(QUESTION, message_id=message_id, thread_id=thread_id)
    return asyncio.run(handle_ask(ctx, event, Intent("ask", {"question": QUESTION}, "collector"), LEAD))


def test_ask_unknown_before_upload_names_priya(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    ask(ctx)
    posts = fake_room.in_thread("h-7")
    assert [(p.agent, p.text) for p in posts] == [
        ("collector", "UNKNOWN for warehouse-2, because no VERIFIED ledger rows match, owned by priya")]
    assert ("explain", {"close_id": CID, "question": QUESTION, "actor": LEAD}) in fake_core.calls


def test_ask_verified_after_upload(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.resolve("G-1", "upload", PRIYA, "h-2", {"path": "x", **G1_PARAMS})
    ask(ctx)
    assert fake_room.in_thread("h-7")[0].text == (
        "Verified ledger facts: CL-0010: warehouse-2 18000 kWh, 3600 kgCO2e, status VERIFIED")


def test_ask_replies_in_question_thread(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    ask(ctx, thread_id="m-4")
    assert len(fake_room.in_thread("m-4")) == 1


def test_ask_no_close(people_config, ctx, fake_core, fake_room):
    ctx.core = AsyncCore(FakeCore(), ctx.core._executor)
    ask(ctx)
    assert [(p.agent, p.text) for p in fake_room.in_thread("h-7")] == [("collector", messages.no_close())]
