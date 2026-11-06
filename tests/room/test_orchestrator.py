# ruff: noqa: E501
"""Close flow orchestrator (SPEC-12 section 6)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from carbon_room import config
from carbon_room.agents.orchestrator import (
    COLLECTOR,
    build_close_graph,
    handle_close_start,
    load_close_config,
)
from carbon_room.models import Actor
from carbon_room.room import messages
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
INTENT = Intent("close.start", {"month": "2026-10"}, "carbon-room")
CID = "2026-10-v1"
SITE_NAMES = ["HQ", "Warehouse-2", "Data Centre EU-West"]
REPO_SITES = Path(__file__).resolve().parents[2] / "config" / "sites.yaml"


def make_event(body, *, message_id="h-1", thread_id=None, sender="@switch-user-lead:test",
               sender_name="lead", attachments=(), addressed=True, receiving_agent="carbon-room"):
    return RoomEvent("message", "!r:test", message_id, thread_id, sender, sender_name, body,
                     tuple(attachments), addressed, 0, receiving_agent, 1)


def run_close(ctx):
    return asyncio.run(handle_close_start(ctx, make_event("@carbon-room close October"), INTENT, LEAD))


@pytest.fixture(autouse=True)
def _cfg(people_config):
    return people_config


def test_close_october_posts_plan_statement_roots_summary_in_order(ctx, fake_core, fake_room):
    run_close(ctx)
    top = fake_room.top_level()
    assert [p.agent for p in top] == ["carbon-room", "collector", "watchdog", "watchdog", "watchdog", "watchdog", "carbon-room"]
    gaps = fake_core.resume_state(CID)[1]
    findings = {f.finding_id: f for f in fake_core.check(CID)}
    roots = [messages.gap_root(g, findings.get(g.finding_id), f"@{g.owner}") for g in gaps]
    expected = [
        messages.close_plan("October 2026", CID, SITE_NAMES, "FS-2026-10"),
        "All 5 October sources collected.",
        *roots,
        messages.summary_post("October 2026", fake_core.summary(CID), ctx.display),
    ]
    assert [p.text for p in top] == expected
    assert all(p.essential is True for p in fake_room.posts)


def test_handoffs_are_targeted(ctx, fake_room):
    run_close(ctx)
    assert fake_room.targeted == [
        ("carbon-room", "collector", "Collect October 2026 for HQ, Warehouse-2, Data Centre EU-West."),
        ("carbon-room", "watchdog", "Check October 2026: every rule, every claim."),
    ]


def test_three_agent_names_post(ctx, fake_room):
    run_close(ctx)
    assert {p.agent for p in fake_room.posts} == {"carbon-room", "collector", "watchdog"}


def test_start_close_gets_event_message_id_and_actor(ctx, fake_core):
    run_close(ctx)
    assert fake_core.calls[0] == ("start_close", {
        "month": "2026-10", "sites": ["hq", "warehouse-2", "dc-eu-west"],
        "factor_set": "FS-2026-10", "actor": LEAD, "chat_message_id": "h-1",
    })


def test_ingest_uses_collector_actor(ctx, fake_core):
    run_close(ctx)
    call = next(c for c in fake_core.calls if c[0] == "ingest")
    assert call[1]["actor"] == Actor("agent", "collector", "Collector")
    assert COLLECTOR == Actor("agent", "collector", "Collector")


def test_core_call_order(ctx, fake_core):
    run_close(ctx)
    assert [c[0] for c in fake_core.calls] == [
        "start_close", "ingest", "calculate", "check", "resume_state",
        "record_gap_thread", "record_gap_thread", "record_gap_thread", "record_gap_thread", "summary",
    ]


def test_begin_close_called(ctx, fake_room):
    run_close(ctx)
    assert fake_room.closes == [CID]


def test_summary_post_equals_summary_output(ctx, fake_core, fake_room):
    run_close(ctx)
    last = fake_room.top_level()[-1].text
    assert last == messages.summary_post("October 2026", fake_core.summary(CID), ctx.display)
    assert "Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0%" in last


def test_on_phase_end_called_after_collect_calculate_summary(ctx, fake_room):
    seen = []
    counts = []

    async def rec(close_id):
        seen.append(close_id)
        counts.append(len(fake_room.posts))

    ctx.on_phase_end = rec
    run_close(ctx)
    assert seen == [CID] * 3
    assert counts == [2, 2, 7]


def test_missing_config_raises_value_error(ctx, fake_core, fake_room, tmp_path, monkeypatch):
    cfg = tmp_path / "only-sites"
    cfg.mkdir()
    (cfg / "sites.yaml").write_text(REPO_SITES.read_text())
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(cfg))
    config.clear_caches()
    with pytest.raises(ValueError, match="config/carbon_room.yaml is missing; P2 provides it"):
        run_close(ctx)
    assert fake_core.calls == []
    assert fake_room.posts == []


def test_missing_default_factor_set(ctx, fake_core, tmp_path, monkeypatch):
    cfg = tmp_path / "nofs"
    cfg.mkdir()
    (cfg / "sites.yaml").write_text(REPO_SITES.read_text())
    (cfg / "carbon_room.yaml").write_text("factor_sets: {}\n")
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(cfg))
    config.clear_caches()
    with pytest.raises(ValueError, match="config/carbon_room.yaml has no default_factor_set"):
        run_close(ctx)
    assert fake_core.calls == []


def test_core_error_propagates(ctx, fake_core, fake_room):
    fake_core.fail["check"] = ValueError("boom")
    with pytest.raises(ValueError, match="boom"):
        run_close(ctx)
    assert [p.agent for p in fake_room.posts] == ["carbon-room", "collector"]


def test_fallback_hint_when_threads_off(ctx, fake_room):
    ctx.threads = False
    run_close(ctx)
    roots = [p for p in fake_room.posts if p.agent == "watchdog"]
    assert len(roots) == 4
    assert all(p.text.endswith("anywhere in the room.") for p in roots)
    assert "Or type `G-2 pick A` anywhere in the room." in roots[1].text


def test_build_close_graph_has_nodes_in_order(ctx):
    nodes = build_close_graph(ctx).get_graph().nodes
    for name in ("plan", "collect", "calculate", "check", "post_gaps", "summary"):
        assert name in nodes


def test_load_close_config():
    assert asyncio.run(load_close_config()) == (
        ["hq", "warehouse-2", "dc-eu-west"], SITE_NAMES, "FS-2026-10",
    )
