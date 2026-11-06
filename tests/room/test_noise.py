# ruff: noqa: E501
"""Noise guard (SPEC-14 section 6)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from fakes.fake_room import FakeRoom

from carbon_room import config
from carbon_room.room.noise import NoiseGuard, max_posts_from_config
from carbon_room.room.ports import Room


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear():
    yield
    config.clear_caches()


def test_noise_full_scripted_close_at_most_12_top_level():
    inner = FakeRoom()
    g = NoiseGuard(inner, max_posts=12, reserve=2)
    g.begin_close("c")

    async def go():
        for i in range(1, 8):
            await g.post("carbon-room", f"e{i}")
        out = [await g.post("carbon-room", f"t{i}", essential=False) for i in range(1, 5)]
        await g.post("carbon-room", "draft")
        await g.post("carbon-room", "publish")
        return out

    out = run(go())
    texts = [p.text for p in inner.top_level()]
    assert len(texts) == 12
    assert texts[7:10] == ["t1", "t2", "t3"]
    assert out[3] == ""
    assert texts[10] == "t4\n\ndraft"
    assert texts[11] == "publish"
    assert g.top_level_count == 12


def test_noise_thread_posts_not_counted():
    inner = FakeRoom()
    g = NoiseGuard(inner)

    async def go():
        for i in range(20):
            await g.post("watchdog", f"x{i}", thread_id="m-1", essential=False)

    run(go())
    assert len(inner.posts) == 20
    assert g.top_level_count == 0


def test_noise_essential_always_sent(caplog):
    inner = FakeRoom()
    g = NoiseGuard(inner)

    async def go():
        for i in range(15):
            await g.post("carbon-room", f"e{i}")

    with caplog.at_level(logging.WARNING):
        run(go())
    assert len(inner.top_level()) == 15
    assert any("limit 12" in r.getMessage() for r in caplog.records)


def test_noise_buffer_joins_multiple():
    inner = FakeRoom()
    g = NoiseGuard(inner, max_posts=3, reserve=2)

    async def go():
        await g.post("carbon-room", "e1")
        await g.post("carbon-room", "t1", essential=False)
        await g.post("carbon-room", "t2", essential=False)
        await g.post("carbon-room", "e2")

    run(go())
    assert [p.text for p in inner.top_level()][1] == "t1\nt2\n\ne2"


def test_begin_close_resets():
    inner = FakeRoom()
    g = NoiseGuard(inner, max_posts=3, reserve=2)

    async def go():
        await g.post("carbon-room", "e1")
        await g.post("carbon-room", "t1", essential=False)
        assert g.buffered == ["t1"]
        g.begin_close("c2")
        assert g.top_level_count == 0
        assert g.buffered == []
        return await g.post("carbon-room", "t2", essential=False)

    assert run(go()) != ""
    assert inner.closes[-1] == "c2"
    assert inner.top_level()[-1].text == "t2"


def test_noise_delegates():
    inner = FakeRoom()
    g = NoiseGuard(inner)
    run(g.send_targeted("carbon-room", "collector", "hi"))
    assert inner.targeted == [("carbon-room", "collector", "hi")]
    assert run(g.upsert_doc("carbon-room", "d", "body")) is True
    assert inner.docs == {"d": "body"}
    assert g.link("m-1") == inner.link("m-1")
    assert isinstance(g, Room)


def test_max_posts_from_config(people_config):
    assert max_posts_from_config() == 12
    (people_config / "carbon_room.yaml").write_text("default_factor_set: FS-2026-10\n")
    config.clear_caches()
    assert max_posts_from_config() == 12


def test_max_posts_from_config_reads_value(people_config):
    (people_config / "carbon_room.yaml").write_text("noise:\n  max_top_level_posts: 9\n")
    config.clear_caches()
    assert max_posts_from_config() == 9
