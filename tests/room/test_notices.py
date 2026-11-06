# ruff: noqa: E501
"""Budget notices (SPEC-14 section 6)."""

from __future__ import annotations

import asyncio

import pytest

from carbon_room import config
from carbon_room.agents.notices import check_budgets, warn_label
from carbon_room.models import Actor

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
CID = "2026-10-v1"


def state(s, used=1):
    return {"used": used, "limit": 200000, "state": s}


@pytest.fixture(autouse=True)
def _cfg(people_config):
    return people_config


def started(fake_core):
    return fake_core.start_close("2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "h-1")


def test_warn_label_from_config(people_config):
    assert asyncio.run(warn_label()) == "80%"
    (people_config / "carbon_room.yaml").write_text("budgets:\n  warn_at: 0.75\n")
    config.clear_caches()
    assert asyncio.run(warn_label()) == "75%"


def test_warn_label_default_without_config(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(empty))
    config.clear_caches()
    assert asyncio.run(warn_label()) == "80%"


def test_budget_warn_once_then_stopped_once(ctx, fake_core, fake_room):
    started(fake_core)
    fake_core.budget = {"collector": state("warn", 160000), "watchdog": state("ok")}
    warn = "@collector has used 80% of its budget for this close."
    stop = "@collector has hit its budget for this close and has stopped. The Lead can raise it in config."
    assert asyncio.run(check_budgets(ctx, CID)) == [warn]
    assert asyncio.run(check_budgets(ctx, CID)) == []
    fake_core.budget = {"collector": state("stopped", 200000), "watchdog": state("ok")}
    assert asyncio.run(check_budgets(ctx, CID)) == [stop]
    assert asyncio.run(check_budgets(ctx, CID)) == []
    assert [(p.agent, p.thread_id, p.essential, p.text) for p in fake_room.posts] == [
        ("carbon-room", None, False, warn),
        ("carbon-room", None, False, stop),
    ]


def test_budget_notices_sorted_by_agent(ctx, fake_core):
    started(fake_core)
    fake_core.budget = {"watchdog": state("warn"), "collector": state("warn")}
    out = asyncio.run(check_budgets(ctx, CID))
    assert out[0].startswith("@collector")
    assert out[1].startswith("@watchdog")


def test_new_close_warns_again(ctx, fake_core):
    started(fake_core)
    fake_core.budget = {"collector": state("warn")}
    assert len(asyncio.run(check_budgets(ctx, CID))) == 1
    v2 = started(fake_core)
    assert v2 == "2026-10-v2"
    assert len(asyncio.run(check_budgets(ctx, v2))) == 1
