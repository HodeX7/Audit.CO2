# ruff: noqa: E501
"""Close Board and phase hook (SPEC-14 section 6)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from fakes.fake_room import FakeRoom

from carbon_room.agents.hooks import after_phase
from carbon_room.agents.orchestrator import handle_close_start
from carbon_room.models import Actor
from carbon_room.room import messages
from carbon_room.room.board import BOARD_NAME, update_board
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
INTENT = Intent("close.start", {"month": "2026-10"}, "carbon-room")
CID = "2026-10-v1"
G1 = {"path": "data/inbox/x.pdf", "site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}


def run_close(ctx):
    ev = RoomEvent("message", "!r:test", "h-1", None, "@switch-user-lead:test", "lead",
                   "@carbon-room close October", (), True, 0, "carbon-room", 1)
    return asyncio.run(handle_close_start(ctx, ev, INTENT, LEAD))


@pytest.fixture(autouse=True)
def _cfg(people_config):
    return people_config


def test_board_after_close(ctx, fake_core, fake_room):
    run_close(ctx)
    assert asyncio.run(update_board(ctx, CID)) is True
    expected = messages.board("October 2026", fake_core.summary(CID), ctx.display, fake_room.link)
    assert fake_room.docs[BOARD_NAME] == expected
    assert BOARD_NAME == "close-board"


def test_board_matches_summary_after_each_resolution(ctx, fake_core, fake_room):
    run_close(ctx)
    steps = [
        ("G-1", "upload", PRIYA, "h-2", G1),
        ("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"}),
        ("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"}),
        ("G-4", "approve", LEAD, "h-5", {}),
    ]
    for gid, action, actor, mid, payload in steps:
        fake_core.resolve(gid, action, actor, mid, payload)
        asyncio.run(update_board(ctx, CID))
        assert fake_room.docs["close-board"] == messages.board(
            "October 2026", fake_core.summary(CID), ctx.display, fake_room.link
        )
    assert "Coverage: 100%" in fake_room.docs["close-board"]
    assert "No open gaps." in fake_room.docs["close-board"]


def test_board_unsupported_returns_false_and_posts_nothing(ctx, fake_core):
    run_close(ctx)
    ctx.room = FakeRoom(supports_docs=False)
    assert asyncio.run(update_board(ctx, CID)) is False
    assert ctx.room.posts == []
    assert ctx.room.docs == {}


def test_after_phase_swallows_errors(ctx, fake_core, fake_room, caplog):
    run_close(ctx)
    fake_core.fail["summary"] = RuntimeError("x")
    fake_core.budget = {"collector": {"used": 160000, "limit": 200000, "state": "warn"}}
    n = len(fake_room.posts)
    with caplog.at_level(logging.ERROR):
        asyncio.run(after_phase(ctx, CID))
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert [p.text for p in fake_room.posts[n:]] == ["@collector has used 80% of its budget for this close."]


def test_after_phase_runs_board_then_budgets(ctx, fake_core):
    run_close(ctx)
    fake_core.calls.clear()
    asyncio.run(after_phase(ctx, CID))
    assert [c[0] for c in fake_core.calls] == ["summary", "budget_usage"]
