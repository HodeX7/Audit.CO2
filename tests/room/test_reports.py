# ruff: noqa: E501
"""Status, trace, audit and help handlers (SPEC-13 section 6)."""

from __future__ import annotations

import asyncio

from fakes.fake_core import FakeCore

from carbon_room.agents.orchestrator import handle_close_start
from carbon_room.agents.reports import handle_help, handle_status, handle_trace, handle_verify_audit
from carbon_room.models import Actor, AuditCheck
from carbon_room.room import messages
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
CID = "2026-10-v1"
G1_PARAMS = {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}


def make_event(body, *, message_id, thread_id=None, attachments=(), receiving_agent="reporter"):
    return RoomEvent("message", "!r:test", message_id, thread_id, "@x:test", "x", body,
                     tuple(attachments), True, 0, receiving_agent, 1)


def run_close(ctx, message_id="h-1"):
    event = make_event("@carbon-room close October", message_id=message_id, receiving_agent="carbon-room")
    return handle_close_start(ctx, event, Intent("close.start", {"month": "2026-10"}, "carbon-room"), LEAD)


def call(handler, ctx, intent, *, message_id="h-5", thread_id=None):
    return asyncio.run(handler(ctx, make_event("x", message_id=message_id, thread_id=thread_id), intent, LEAD))


def test_status_reply_in_thread(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    call(handle_status, ctx, Intent("close.status", {}, "carbon-room"))
    posts = fake_room.in_thread("h-5")
    assert len(posts) == 1
    assert posts[0].agent == "carbon-room"
    assert posts[0].text == messages.summary_post("October 2026", fake_core.summary(CID), ctx.display)


def test_status_inside_a_thread_replies_there(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    call(handle_status, ctx, Intent("close.status", {}, "carbon-room"), thread_id="m-4")
    assert len(fake_room.in_thread("m-4")) == 1


def test_trace_card_and_unknown_tag(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.resolve("G-1", "upload", PRIYA, "h-2", {"path": "x", **G1_PARAMS})
    fake_core.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    fake_core.resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})
    fake_core.resolve("G-4", "approve", LEAD, "h-5", {})
    fake_core.draft_report(CID)
    call(handle_trace, ctx, Intent("report.trace", {"tag": "S-001"}, "reporter"), message_id="h-6")
    call(handle_trace, ctx, Intent("report.trace", {"tag": "S-099"}, "reporter"), message_id="h-7")
    reporter = [p for p in fake_room.posts if p.agent == "reporter"]
    assert reporter[0].text == messages.trace_card(fake_core.trace(CID, "S-001"), "message h-5")
    assert reporter[1].text == "I can't find S-099 in this close."


def test_verify_audit_reply(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.audit = AuditCheck(False, 9, 4)
    call(handle_verify_audit, ctx, Intent("audit.verify", {}, "reporter"))
    posts = fake_room.in_thread("h-5")
    assert [(p.agent, p.text) for p in posts] == [("reporter", "Audit chain broken at event 4 (9 events checked).")]


def test_help_reply_uses_target_agent(people_config, ctx, fake_core, fake_room):
    reason = "I don't know the month 'Smarch'."
    call(handle_help, ctx, Intent("help", {"reason": reason}, "watchdog"))
    posts = fake_room.in_thread("h-5")
    assert [(p.agent, p.text) for p in posts] == [("watchdog", messages.help_text(reason))]
    assert fake_core.calls == []


def test_no_close_replies(people_config, ctx, fake_core, fake_room):
    ctx.core = AsyncCore(FakeCore(), ctx.core._executor)
    call(handle_status, ctx, Intent("close.status", {}, "carbon-room"), message_id="h-1")
    call(handle_trace, ctx, Intent("report.trace", {"tag": "S-001"}, "reporter"), message_id="h-2")
    call(handle_verify_audit, ctx, Intent("audit.verify", {}, "reporter"), message_id="h-3")
    got = [(p.thread_id, p.agent, p.text) for p in fake_room.posts]
    assert got == [("h-1", "carbon-room", messages.no_close()), ("h-2", "reporter", messages.no_close()),
                   ("h-3", "reporter", messages.no_close())]
