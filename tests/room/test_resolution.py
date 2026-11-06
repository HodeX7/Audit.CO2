# ruff: noqa: E501
"""Gap reply resolution (SPEC-13 section 6)."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import date
from decimal import Decimal

import pytest
from fakes.fake_core import FakeCore, _r6_finding

from carbon_room.agents.orchestrator import handle_close_start
from carbon_room.agents.resolution import handle_gap_reply
from carbon_room.models import Actor, Finding, LockHeld, Option
from carbon_room.room import grammar, messages
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.events import Attachment, RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
GUEST = Actor("human", "guest:@x:test", "x", None)

WH2_FILE = "warehouse2_electricity_2026-10_actual.pdf"
G1_PARAMS = {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}
R7 = Finding("F-0000000007", "R7", "FINANCE", ["CL-0004"], "hq", "2026-10", "finance",
             "HQ electricity needs finance sign-off", ["Amount: 9660"],
             [Option("approve", "approve", "Sign off")], 2, False)
CHECKING = "Checking…"
RESOLVED_G2 = "Resolved. G-2 is closed and the ledger is updated."
NOT_OWNER = "Only the Lead or the gap owner (@lead) can do that."


def make_event(body, *, message_id, thread_id=None, attachments=(), receiving_agent="watchdog"):
    return RoomEvent("message", "!r:test", message_id, thread_id, "@x:test", "x", body,
                     tuple(attachments), True, 0, receiving_agent, 1)


def run_close(ctx, message_id="h-1"):
    event = make_event("@carbon-room close October", message_id=message_id, receiving_agent="carbon-room")
    return handle_close_start(ctx, event, Intent("close.start", {"month": "2026-10"}, "carbon-room"), LEAD)


def root(fake_room, gap_id):
    for p in reversed(fake_room.top_level()):
        if p.agent == "watchdog" and p.text.startswith(f"**{gap_id} "):
            return p.message_id
    raise AssertionError(f"no root for {gap_id}")


def reply(ctx, actor, body, *, thread, message_id, attachments=()):
    event = make_event(body, message_id=message_id, thread_id=thread, attachments=attachments)
    intent = grammar.parse(body, in_thread=thread is not None, today=date(2026, 11, 5))
    return handle_gap_reply(ctx, event, intent, actor)


def fallback(ctx, actor, body, *, message_id):
    event = make_event(body, message_id=message_id)
    intent = grammar.parse(body, in_thread=False, today=date(2026, 11, 5))
    assert intent.kind == "gap.fallback"
    return handle_gap_reply(ctx, event, intent, actor)


def texts(fake_room, thread):
    return [p.text for p in fake_room.in_thread(thread)]


def names(fake_core, start=0):
    return [c[0] for c in fake_core.calls[start:]]


@pytest.fixture
def started(people_config, ctx):
    asyncio.run(run_close(ctx))
    return ctx


def test_pick_a_in_diesel_thread_calls_resolve_with_option_a(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    asyncio.run(reply(ctx, LEAD, "pick a", thread=root(fake_room, "G-2"), message_id="h-2"))
    assert ("resolve", {"gap_id": "G-2", "action": "pick", "actor": LEAD, "chat_message_id": "h-2",
                        "payload": {"claim_id": "CL-0003"}}) in fake_core.calls
    posts = fake_room.in_thread("m-4")
    assert [p.text for p in posts] == [CHECKING, RESOLVED_G2]
    assert all(p.agent == "watchdog" for p in posts)


def test_hello_in_gap_thread_lists_options_and_no_resolve(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    n = len(fake_core.calls)
    asyncio.run(reply(ctx, LEAD, "hello", thread="m-4", message_id="h-2"))
    assert texts(fake_room, "m-4") == ["I didn't catch that. Reply with one of: `pick A`, `pick B`."]
    assert "resolve" not in names(fake_core, n)
    assert "summary" not in names(fake_core, n)


def test_already_resolved_and_no_options(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-2"))
    asyncio.run(reply(ctx, LEAD, "pick b", thread="m-4", message_id="h-3"))
    assert texts(fake_room, "m-4")[-1] == "G-2 is already resolved."
    fake_core.on_resolve_open = [dataclasses.replace(_r6_finding("2026-10"), finding_id="F-0000000008")]
    asyncio.run(reply(ctx, LEAD, "approve", thread="m-6", message_id="h-4"))
    g5 = root(fake_room, "G-5")
    asyncio.run(reply(ctx, LEAD, "approve", thread=g5, message_id="h-5"))
    assert texts(fake_room, g5) == ["No reply needed here."]


def test_reply_outside_a_gap_thread_is_silent(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    posts, n = len(fake_room.posts), len(fake_core.calls)
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-7", message_id="h-2"))
    assert len(fake_room.posts) == posts
    assert "resolve" not in names(fake_core, n)


def test_fallback_in_channel_routes_and_replies_in_gap_thread(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx, "h-1"))
    asyncio.run(run_close(ctx, "h-8"))
    asyncio.run(fallback(ctx, LEAD, "G-2 pick A", message_id="h-9"))
    assert texts(fake_room, "m-11") == [CHECKING, RESOLVED_G2]
    assert "G-2" in [g.gap_id for g in fake_core.resume_state("2026-10-v1")[1]]


def test_reply_in_old_close_thread_is_refused(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx, "h-1"))
    asyncio.run(run_close(ctx, "h-8"))
    n = len(fake_core.calls)
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-9"))
    assert texts(fake_room, "m-4") == [
        "G-2 belongs to an earlier close (2026-10-v1). Reply in the thread from the current close."]
    assert "resolve" not in names(fake_core, n)


def test_fallback_unknown_gap_and_no_close(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    asyncio.run(fallback(ctx, LEAD, "G-9 approve", message_id="h-3"))
    assert texts(fake_room, "h-3") == ["I can't find an open G-9 in this close."]
    ctx.core = AsyncCore(FakeCore(), ctx.core._executor)
    asyncio.run(fallback(ctx, LEAD, "G-2 pick A", message_id="h-4"))
    assert texts(fake_room, "h-4") == [messages.no_close()]


def test_guest_refused_without_core_call(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    n = len(fake_core.calls)
    asyncio.run(reply(ctx, GUEST, "pick a", thread="m-4", message_id="h-2"))
    assert texts(fake_room, "m-4") == [NOT_OWNER]
    assert names(fake_core, n) == ["gap_for_thread", "latest_close"]


def test_priya_resolving_g2_is_not_allowed(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    asyncio.run(reply(ctx, PRIYA, "pick a", thread="m-4", message_id="h-2"))
    assert texts(fake_room, "m-4") == [CHECKING, NOT_OWNER]


def _inbox(tmp_path, monkeypatch, *, write=True):
    monkeypatch.chdir(tmp_path)
    inbox = tmp_path / "data" / "inbox"
    inbox.mkdir(parents=True)
    if write:
        (inbox / WH2_FILE).write_bytes(b"pdf")


def _attachment():
    return Attachment(WH2_FILE, "application/pdf", 10, "mxc://s/1", "m.file")


def _resolve_call(fake_core):
    return next(a for n, a in fake_core.calls if n == "resolve")


def test_upload_with_inbox_file_passes_path(people_config, ctx, fake_core, fake_room, tmp_path, monkeypatch):
    asyncio.run(run_close(ctx))
    _inbox(tmp_path, monkeypatch)
    asyncio.run(reply(ctx, PRIYA, "", thread="m-3", message_id="h-2", attachments=(_attachment(),)))
    call = _resolve_call(fake_core)
    assert call["gap_id"] == "G-1"
    assert call["action"] == "upload"
    assert call["actor"] == PRIYA
    assert call["chat_message_id"] == "h-2"
    assert call["payload"] == {**G1_PARAMS, "path": f"data/inbox/{WH2_FILE}"}


def test_upload_typed_name_inbox(people_config, ctx, fake_core, fake_room, tmp_path, monkeypatch):
    asyncio.run(run_close(ctx))
    _inbox(tmp_path, monkeypatch)
    asyncio.run(reply(ctx, PRIYA, f"upload {WH2_FILE}", thread="m-3", message_id="h-2"))
    assert _resolve_call(fake_core)["payload"] == {**G1_PARAMS, "path": f"data/inbox/{WH2_FILE}"}


def test_upload_missing_file_exact_text(people_config, ctx, fake_core, fake_room, tmp_path, monkeypatch):
    asyncio.run(run_close(ctx))
    _inbox(tmp_path, monkeypatch, write=False)
    asyncio.run(reply(ctx, PRIYA, "", thread="m-3", message_id="h-2", attachments=(_attachment(),)))
    assert texts(fake_room, "m-3") == [
        CHECKING, f"I can't see that file yet. Put it in data/inbox/ and reply upload {WH2_FILE}."]
    assert "resolve" not in names(fake_core)


def test_outcome_resolved_and_still_open(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.keep_open = {"G-4"}
    asyncio.run(reply(ctx, LEAD, "approve", thread="m-6", message_id="h-2"))
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-3"))
    assert texts(fake_room, "m-6")[-1] == "G-4 is still open: HQ October electricity is 38% above September."
    assert texts(fake_room, "m-4")[-1] == RESOLVED_G2


def test_new_gaps_from_resolve_are_posted(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.on_resolve_open = [R7]
    asyncio.run(reply(ctx, LEAD, "approve", thread="m-6", message_id="h-2"))
    g5 = next(g for g in fake_core.resume_state("2026-10-v1")[1] if g.gap_id == "G-5")
    assert fake_room.top_level()[-1].text == messages.gap_root(g5, R7, "@finance")
    assert fake_room.top_level()[-1].agent == "watchdog"
    assert fake_core.gap_for_thread(root(fake_room, "G-5")).gap_id == "G-5"


def test_total_moved_posted_once_when_changed(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    before = len(fake_room.top_level())
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-2"))
    new = fake_room.top_level()[before:]
    assert len(new) == 1
    assert new[0].agent == "carbon-room"
    assert new[0].essential is False
    assert new[0].text == "Total moved 0.0 → 5.3 tCO2e, coverage 0% → 23%."


def test_reject_posts_no_total_line(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    before = len(fake_room.top_level())
    asyncio.run(reply(ctx, LEAD, "reject: not ours", thread="m-5", message_id="h-2"))
    assert len(fake_room.top_level()) == before
    assert _resolve_call(fake_core)["payload"] == {"reason": "not ours"}


def test_four_scripted_resolutions_reach_fake_final_totals(people_config, ctx, fake_core, fake_room, tmp_path, monkeypatch):
    asyncio.run(run_close(ctx))
    _inbox(tmp_path, monkeypatch)
    asyncio.run(reply(ctx, PRIYA, "", thread="m-3", message_id="h-2", attachments=(_attachment(),)))
    asyncio.run(reply(ctx, LEAD, "pick A", thread="m-4", message_id="h-3"))
    asyncio.run(reply(ctx, LEAD, "approve", thread="m-5", message_id="h-4"))
    asyncio.run(reply(ctx, LEAD, "approve", thread="m-6", message_id="h-5"))
    s = fake_core.summary("2026-10-v1")
    assert s.verified_kgco2e == Decimal("22900")
    assert s.coverage_pct == Decimal("100")
    assert [p.text for p in fake_room.top_level() if not p.essential] == [
        "Total moved 0.0 → 3.6 tCO2e, coverage 0% → 12%.",
        "Total moved 3.6 → 8.9 tCO2e, coverage 12% → 39%.",
        "Total moved 8.9 → 13.2 tCO2e, coverage 39% → 58%.",
        "Total moved 13.2 → 22.9 tCO2e, coverage 58% → 100%.",
    ]


def test_resolve_error_replied_in_thread(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.fail["resolve"] = LockHeld("x")
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-2"))
    assert texts(fake_room, "m-4") == [CHECKING, "@collector is still reading that source. Try again in a moment."]


def test_unexpected_error_propagates(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    fake_core.fail["resolve"] = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-2"))


def test_on_phase_end_after_resolution(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    seen: list[str] = []

    async def recorder(close_id):
        seen.append(close_id)

    ctx.on_phase_end = recorder
    asyncio.run(reply(ctx, LEAD, "pick a", thread="m-4", message_id="h-2"))
    assert seen == ["2026-10-v1"]
