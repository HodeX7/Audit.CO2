# ruff: noqa: E501
"""Draft and publish handlers (SPEC-13 section 6)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fakes.fake_core import FakeCore

from carbon_room.agents.orchestrator import handle_close_start
from carbon_room.agents.publish import handle_draft, handle_publish, list_outputs
from carbon_room.models import Actor
from carbon_room.room import messages
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
GUEST = Actor("human", "guest:@x:test", "x", None)
CID = "2026-10-v1"
LEAD_ONLY = "Only the Lead can do that."


def make_event(body, *, message_id, thread_id=None, attachments=(), receiving_agent="reporter"):
    return RoomEvent("message", "!r:test", message_id, thread_id, "@x:test", "x", body,
                     tuple(attachments), True, 0, receiving_agent, 1)


def run_close(ctx, message_id="h-1"):
    event = make_event("@carbon-room close October", message_id=message_id, receiving_agent="carbon-room")
    return handle_close_start(ctx, event, Intent("close.start", {"month": "2026-10"}, "carbon-room"), LEAD)


def draft(ctx, actor=LEAD, message_id="h-5"):
    return handle_draft(ctx, make_event("@reporter draft", message_id=message_id), Intent("report.draft", {}, "reporter"), actor)


def publish(ctx, actor=LEAD, message_id="h-6"):
    return handle_publish(ctx, make_event("@carbon-room publish", message_id=message_id, receiving_agent="carbon-room"),
                          Intent("close.publish", {}, "carbon-room"), actor)


def names(fake_core, start=0):
    return [c[0] for c in fake_core.calls[start:]]


def test_draft_posts_headline(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    before = len(fake_room.top_level())
    asyncio.run(draft(ctx))
    new = fake_room.top_level()[before:]
    assert len(new) == 1
    assert new[0].agent == "reporter"
    assert new[0].text == messages.draft(fake_core.draft_report(CID), "October 2026")
    assert new[0].text.startswith("**Draft v1 for October 2026**")


def test_lead_publishes_and_paths_listed(people_config, ctx, fake_core, fake_room, tmp_path, monkeypatch):
    asyncio.run(run_close(ctx))
    monkeypatch.chdir(tmp_path)
    out = Path("out/2026-10/v1")
    out.mkdir(parents=True)
    (out / "report.md").write_text("r")
    (out / "coverage.html").write_text("c")
    ctx.out_dir = Path("out")
    before = len(fake_room.top_level())
    asyncio.run(publish(ctx))
    new = fake_room.top_level()[before:]
    assert len(new) == 1
    assert new[0].agent == "carbon-room"
    assert new[0].text == (
        "Published v1 by @lead.\n"
        "Verified: 0.0 tCO2e · Coverage: 0% · 0 of 4 expected sources verified\n"
        "Published with 4 open gap(s); their rows are excluded.\n"
        "Files: out/2026-10/v1/coverage.html, out/2026-10/v1/report.md"
    )
    call = next(a for n, a in fake_core.calls if n == "publish")
    assert call["actor"] == LEAD
    assert call["chat_message_id"] == "h-6"


def test_publish_drafts_first_when_needed(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    n = len(fake_core.calls)
    asyncio.run(publish(ctx))
    assert names(fake_core, n) == ["latest_close", "resume_state", "draft_report", "publish"]


def test_publish_after_draft_does_not_redraft(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    asyncio.run(draft(ctx))
    n = len(fake_core.calls)
    asyncio.run(publish(ctx))
    assert names(fake_core, n) == ["latest_close", "resume_state", "publish"]


def test_guest_publish_refused(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    n = len(fake_core.calls)
    asyncio.run(publish(ctx, GUEST))
    posts = fake_room.in_thread("h-6")
    assert [(p.agent, p.text) for p in posts] == [("carbon-room", LEAD_ONLY)]
    assert len(fake_core.calls) == n


def test_priya_publish_not_allowed_text(people_config, ctx, fake_core, fake_room):
    asyncio.run(run_close(ctx))
    before = len(fake_room.top_level())
    asyncio.run(publish(ctx, PRIYA))
    assert [p.text for p in fake_room.in_thread("h-6")] == [LEAD_ONLY]
    assert len(fake_room.top_level()) == before


def test_list_outputs(tmp_path):
    base = tmp_path / "out" / "2026-10" / "v1"
    (base / "sub").mkdir(parents=True)
    (base / "a.txt").write_text("a")
    (base / "sub" / "b.txt").write_text("b")
    got = asyncio.run(list_outputs(tmp_path / "out", CID, 1))
    assert got == sorted([(base / "a.txt").as_posix(), (base / "sub" / "b.txt").as_posix()])
    assert asyncio.run(list_outputs(tmp_path / "out", CID, 2)) == []


def test_draft_and_publish_no_close(people_config, ctx, fake_core, fake_room):
    ctx.core = AsyncCore(FakeCore(), ctx.core._executor)
    asyncio.run(draft(ctx, message_id="h-1"))
    asyncio.run(publish(ctx, message_id="h-2"))
    assert [(p.agent, p.text) for p in fake_room.in_thread("h-1")] == [("reporter", messages.no_close())]
    assert [(p.agent, p.text) for p in fake_room.in_thread("h-2")] == [("carbon-room", messages.no_close())]
