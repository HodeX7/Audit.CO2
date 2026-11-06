"""Gap root posting (SPEC-12 section 6)."""

from __future__ import annotations

import asyncio
import logging

from fakes.fake_room import FakeRoom

from carbon_room.agents.gaps import gap_number, post_new_gaps
from carbon_room.models import Actor, Finding, Option
from carbon_room.room import messages

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")


def arrange(fake_core):
    cid = fake_core.start_close("2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "h-1")
    fake_core.ingest(cid, Actor("agent", "collector", "Collector"))
    fake_core.calculate(cid)
    return cid, fake_core.check(cid)


def test_gap_roots_recorded_in_core(ctx, fake_core):
    cid, findings = arrange(fake_core)
    assert asyncio.run(post_new_gaps(ctx, cid, findings)) == ["G-1", "G-2", "G-3", "G-4"]
    for n in range(1, 5):
        assert fake_core.gap_for_thread(f"m-{n}").gap_id == f"G-{n}"


def test_post_new_gaps_twice_posts_once(ctx, fake_core, fake_room):
    cid, findings = arrange(fake_core)
    asyncio.run(post_new_gaps(ctx, cid, findings))
    assert asyncio.run(post_new_gaps(ctx, cid, findings)) == []
    assert len(fake_room.posts) == 4


def test_roots_use_owner_display_and_evidence(ctx, fake_core, fake_room):
    cid, findings = arrange(fake_core)
    ctx.display = lambda pid: {"priya": "@priya.k"}.get(pid, pid)
    asyncio.run(post_new_gaps(ctx, cid, findings))
    g1 = fake_core.resume_state(cid)[1][0]
    assert fake_room.posts[0].text == messages.gap_root(g1, findings[0], "@priya.k")


def test_new_gap_without_finding_posts_without_evidence(ctx, fake_core, fake_room):
    cid, findings = arrange(fake_core)
    assert len(asyncio.run(post_new_gaps(ctx, cid, findings))) == 4
    fake_core.on_resolve_open = [
        Finding(
            "F-0000000007", "R7", "FINANCE", ["CL-0004"], "hq", "2026-10", "finance",
            "HQ electricity needs finance sign-off", ["Amount: 9660"],
            [Option("approve", "approve", "Sign off")], 2, False,
        )
    ]
    fake_core.resolve("G-4", "approve", LEAD, "h-2", {})
    assert asyncio.run(post_new_gaps(ctx, cid, [])) == ["G-5"]
    assert "Evidence:" not in fake_room.posts[-1].text


def test_empty_message_id_is_not_recorded(ctx, fake_core, caplog):
    class Silent(FakeRoom):
        async def post(self, agent, text, *, thread_id=None, essential=True):
            await super().post(agent, text, thread_id=thread_id, essential=essential)
            return ""

    ctx.room = Silent()
    cid, findings = arrange(fake_core)
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(post_new_gaps(ctx, cid, findings)) == []
    assert "record_gap_thread" not in [c[0] for c in fake_core.calls]
    assert any(
        r.levelno == logging.WARNING and "gap G-1 root not posted" in r.getMessage() for r in caplog.records
    )


def test_record_error_is_logged_and_continues(ctx, fake_core, caplog):
    cid, findings = arrange(fake_core)
    fake_core.fail["record_gap_thread"] = ValueError("taken")
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(post_new_gaps(ctx, cid, findings)) == ["G-2", "G-3", "G-4"]
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_gap_number():
    assert (gap_number("G-12"), gap_number("G-2"), gap_number("bad")) == (12, 2, 10**9)
