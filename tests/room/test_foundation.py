"""Frames, ports, AsyncCore, FakeRoom and fixtures (SPEC-01 section 6)."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fakes.fake_core import FakeCore
from fakes.fake_room import FakeRoom

from carbon_room import config
from carbon_room.models import Actor, NotFound
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.frames import frame_fields, frame_kind, pong, sequence_of
from carbon_room.room.ports import AGENT_NAMES, AGENT_TITLES, Context, Room

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")


def test_frames_kind_and_fields_both_envelopes():
    ping = {"type": "ping"}
    assert (frame_kind(ping), frame_fields(ping), sequence_of(ping)) == ("ping", {}, None)
    msg = {"event": "message", "data": {"type": "message", "payload": {}, "sequence": 7}, "id": 7}
    assert frame_kind(msg) == "message"
    assert frame_fields(msg) is msg["data"]
    assert sequence_of(msg) == 7
    evicted = {"event": "evicted", "data": {"code": "heartbeat_lapsed"}}
    assert frame_kind(evicted) == "evicted"
    assert frame_fields(evicted) == {"code": "heartbeat_lapsed"}
    state = {"type": "connection_state", "generation": 3, "cursor": 10}
    assert frame_kind(state) == "connection_state"
    assert frame_fields(state) == {"generation": 3, "cursor": 10}


def test_frames_domain_type_wins_over_event():
    assert frame_kind({"event": "message", "data": {"type": "command", "sequence": 9}, "id": 9}) == "command"
    assert frame_kind({"event": "room_join", "data": {"type": "room_join"}}) == "room_join"


@pytest.mark.parametrize("frame", [{}, {"type": "nope"}, {"event": 5}, {"data": "x"}, [], None, "ping"])
def test_frames_garbage(frame):
    assert frame_kind(frame) is None
    if not isinstance(frame, dict):
        assert frame_fields(frame) == {}
    assert sequence_of(frame) is None


def test_sequence_of_variants():
    assert sequence_of({"id": "12"}) == 12
    assert sequence_of({"id": True}) is None
    assert sequence_of({"data": {"sequence": 5}}) == 5
    assert sequence_of({"id": "x", "data": {"sequence": "6"}}) == 6


def test_frame_fields_drops_private_keys():
    assert frame_fields({"_source": "docs", "type": "ping", "x": 1}) == {"x": 1}


def test_pong_payload():
    assert json.loads(pong(42)) == {"type": "pong", "cursor": 42}


def test_context_defaults():
    a = Context(core=None, room=FakeRoom())
    b = Context(core=None, room=FakeRoom())
    assert a.threads is True
    assert a.attachments_mode == "inbox"
    assert a.inbox_dir == Path("data/inbox")
    assert a.out_dir == Path("out")
    assert a.state == {}
    assert a.display("x") == "x"
    assert a.today() == datetime.now(timezone.utc).date()
    assert asyncio.run(a.on_phase_end("c")) is None
    a.state["k"] = 1
    assert b.state == {}


def test_agent_names_and_titles():
    assert AGENT_NAMES == ("carbon-room", "collector", "watchdog", "reporter")
    assert set(AGENT_TITLES) == set(AGENT_NAMES)


def test_async_core_runs_in_worker_thread():
    class Obj:
        def latest_close(self):
            return threading.current_thread().name, threading.get_ident()

    async def go():
        return await AsyncCore(Obj()).latest_close(), threading.get_ident()

    (name, ident), main_ident = asyncio.run(go())
    assert ident != main_ident
    assert name.startswith("core")


def test_async_core_passes_args():
    fc = FakeCore()
    asyncio.run(AsyncCore(fc).ingest_file("c", "p", LEAD, "h", site="hq"))
    assert fc.calls[-1][1]["site"] == "hq"


def test_async_core_rejects_unknown_name():
    with pytest.raises(AttributeError):
        AsyncCore(object()).connect


def test_async_core_propagates_exceptions():
    fc = FakeCore()
    fc.fail["summary"] = e = NotFound("x")
    with pytest.raises(NotFound) as exc:
        asyncio.run(AsyncCore(fc).summary("c"))
    assert exc.value is e


def test_async_core_uses_given_executor():
    class Obj:
        def latest_close(self):
            return threading.current_thread().name

    executor = ThreadPoolExecutor(1, thread_name_prefix="given")
    try:
        name = asyncio.run(AsyncCore(Obj(), executor).latest_close())
    finally:
        executor.shutdown(wait=True)
    assert name.startswith("given")


def test_fake_room_ids_and_queries():
    room = FakeRoom()

    async def go():
        return [
            await room.post("carbon-room", "a"),
            await room.post("watchdog", "b", thread_id="m-1"),
            await room.post("reporter", "c"),
        ]

    assert asyncio.run(go()) == ["m-1", "m-2", "m-3"]
    assert [p.agent for p in room.top_level()] == ["carbon-room", "reporter"]
    in_thread = room.in_thread("m-1")
    assert len(in_thread) == 1 and in_thread[0].essential is True
    assert room.link("m-2") == "message m-2"


def test_fake_room_targeted_docs_closes():
    no_docs = FakeRoom(supports_docs=False)
    docs = FakeRoom()

    async def go():
        await no_docs.send_targeted("carbon-room", "collector", "hi")
        first = await no_docs.upsert_doc("carbon-room", "close-board", "x")
        second = await docs.upsert_doc("carbon-room", "close-board", "x")
        return first, second

    first, second = asyncio.run(go())
    docs.begin_close("c-1")
    assert no_docs.targeted == [("carbon-room", "collector", "hi")]
    assert first is False and no_docs.docs == {}
    assert second is True and docs.docs == {"close-board": "x"}
    assert docs.closes == ["c-1"]


def test_fake_room_satisfies_room_protocol():
    assert isinstance(FakeRoom(), Room)


def test_people_config_fixture(people_config):
    people = config.load_people()["people"]
    assert len(people) == 4
    assert people[0]["id"] == "lead"
    assert config.load_config()["noise"]["max_top_level_posts"] == 12
    assert os.environ["CARBON_ROOM_CONFIG_DIR"] == str(people_config)


def test_ctx_fixture(ctx, fake_core):
    assert asyncio.run(ctx.core.latest_close()) is None
    assert ctx.display("priya") == "@priya"
    assert ctx.today() == date(2026, 11, 5)
