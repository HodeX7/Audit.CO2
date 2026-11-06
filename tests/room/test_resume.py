# ruff: noqa: E501
"""Resume (SPEC-14 section 6)."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from fakes.fake_room import FakeRoom

from carbon_room.agents.orchestrator import handle_close_start, handle_resume, resume, resume_on_startup
from carbon_room.models import Actor, Finding, Option
from carbon_room.room import messages
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
INTENT = Intent("close.start", {"month": "2026-10"}, "carbon-room")
CID = "2026-10-v1"
RESUME_TEXT = (
    "Resuming the October 2026 close at AWAITING_HUMANS.\n"
    "Open gaps: G-1 @priya (message m-3) · G-2 @lead (message m-4) · G-3 @lead (message m-5) · G-4 @lead (message m-6)"
)
G1 = {"path": "data/inbox/x.pdf", "site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}


def make_event(body, *, message_id="h-1", thread_id=None):
    return RoomEvent("message", "!r:test", message_id, thread_id, "@switch-user-lead:test", "lead", body,
                     (), True, 0, "carbon-room", 1)


def run_close(ctx):
    return asyncio.run(handle_close_start(ctx, make_event("@carbon-room close October"), INTENT, LEAD))


@pytest.fixture(autouse=True)
def _cfg(people_config):
    return people_config


def test_resume_line_lists_open_gaps_with_links_and_posts_no_roots(ctx, fake_core):
    run_close(ctx)
    n_calls = len(fake_core.calls)
    room2 = FakeRoom()
    ctx2 = dataclasses.replace(ctx, room=room2)
    asyncio.run(resume(ctx2, CID))
    assert len(room2.posts) == 1
    p = room2.posts[0]
    assert (p.agent, p.thread_id, p.text) == ("carbon-room", None, RESUME_TEXT)
    assert not [c for c in fake_core.calls[n_calls:] if c[0] == "record_gap_thread"]


def test_resume_posts_missing_root_once(ctx, fake_core):
    run_close(ctx)
    fake_core.on_resolve_open = [
        Finding(
            "F-0000000007", "R7", "FINANCE", ["CL-0004"], "hq", "2026-10", "finance",
            "HQ electricity needs finance sign-off", ["Amount: 9660"],
            [Option("approve", "approve", "Sign off")], 2, False,
        )
    ]
    fake_core.resolve("G-4", "approve", LEAD, "h-2", {})
    room2 = FakeRoom()
    ctx2 = dataclasses.replace(ctx, room=room2)
    asyncio.run(resume(ctx2, CID))
    assert len(room2.posts) == 2
    assert "G-5 @finance (no thread yet)" in room2.posts[0].text
    assert room2.posts[1].text.startswith("**G-5 · FINANCE**")
    assert "Evidence:" not in room2.posts[1].text
    asyncio.run(resume(ctx2, CID))
    assert len(room2.posts) == 3
    assert "G-5 @finance (message m-2)" in room2.posts[2].text


def test_handle_resume_no_close(ctx, fake_room):
    asyncio.run(handle_resume(ctx, make_event("@carbon-room resume"), Intent("resume", {}, "carbon-room"), LEAD))
    assert [(p.agent, p.thread_id, p.text) for p in fake_room.posts] == [("carbon-room", "h-1", messages.no_close())]


def test_handle_resume_does_not_begin_close(ctx, fake_room):
    run_close(ctx)
    asyncio.run(handle_resume(ctx, make_event("@carbon-room resume", message_id="h-7"), Intent("resume", {}, "carbon-room"), LEAD))
    assert fake_room.closes == [CID]


def test_resume_on_startup_true_false_published(ctx, fake_core):
    room_a = FakeRoom()
    ctx_a = dataclasses.replace(ctx, room=room_a)
    assert asyncio.run(resume_on_startup(ctx_a)) is False
    assert room_a.posts == []

    run_close(ctx)
    room2 = FakeRoom()
    ctx2 = dataclasses.replace(ctx, room=room2)
    assert asyncio.run(resume_on_startup(ctx2)) is True
    assert room2.closes == [CID]
    assert len(room2.posts) == 1
    assert room2.posts[0].text.startswith("Resuming the October 2026 close")

    fake_core.resolve("G-1", "upload", PRIYA, "h-2", G1)
    fake_core.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    fake_core.resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})
    fake_core.resolve("G-4", "approve", LEAD, "h-5", {})
    fake_core.draft_report(CID)
    fake_core.publish(CID, LEAD, "h-9")
    room3 = FakeRoom()
    ctx3 = dataclasses.replace(ctx, room=room3)
    assert asyncio.run(resume_on_startup(ctx3)) is False
    assert room3.posts == []
    assert room3.closes == []
