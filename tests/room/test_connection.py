"""AgentConnection against the fake Switch server (SPEC-07 section 6)."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from contextlib import asynccontextmanager

import pytest
from fakes.fake_switch import FakeSwitch
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from carbon_room.room import frames
from carbon_room.room.connection import AgentConnection, AuthError, backoff_delays

KEY = "sk-test-secret"
DELAYS: list[float] = []


@pytest.fixture(autouse=True)
def _reset_delays():
    DELAYS.clear()
    yield


async def fast_sleep(d: float) -> None:
    DELAYS.append(d)
    await asyncio.sleep(0.01)


def make_conn(server, agent_id="agent-cr", key=KEY, filter="addressed", received=None, **kw):
    sink = received if received is not None else []
    kw.setdefault("sleep", fast_sleep)
    on_event = kw.pop("on_event", None) or (lambda a, f: sink.append((a, f)))
    return AgentConnection("carbon-room", agent_id, key, server, ["room-1"], filter, on_event, **kw)


def run_async(coro):
    async def wrapped():
        return await asyncio.wait_for(coro, 5)

    return asyncio.run(wrapped())


@asynccontextmanager
async def fake_switch(**kw):
    kw.setdefault("ping_interval", 0.2)
    kw.setdefault("evict_after", 0.6)
    fake = FakeSwitch(**kw)
    server = await fake.start()
    try:
        yield fake, server
    finally:
        await fake.stop()


@asynccontextmanager
async def running(conn, *, wait_connected=True):
    task = asyncio.create_task(conn.run())
    try:
        if wait_connected:
            await asyncio.wait_for(conn.connected.wait(), 2)
        yield task
    finally:
        await conn.stop()
        try:
            await asyncio.wait_for(task, 2)
        except AuthError:
            pass


def msg(fake, body, mid):
    return fake.message(body=body, message_id=mid)


def test_url_scheme_and_query():
    conn = AgentConnection(
        "carbon-room", "agent-cr", KEY, "https://h.example/base/", ["room-1"], "addressed",
        lambda a, f: None, connection_id="c-1",
    )
    base = (
        "wss://h.example/base/agents/agent-cr/connection/ws?connection_id=c-1&rooms=room-1"
        "&filter=addressed&client=carbon-room-python&client_version=0.1.0"
    )
    assert conn.url() == base
    conn.cursor = 5
    conn.generation = 2
    assert conn.url() == base + "&start_from=5&expected_generation=2"


def test_sends_auth_and_query():
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            async with running(conn):
                pass
            rec = fake.connections[0]
            assert rec.auth == f"Bearer {KEY}"
            assert rec.query["rooms"] == "room-1"
            assert rec.query["filter"] == "addressed"
            assert rec.query["client"] == "carbon-room-python"
            assert "start_from" not in rec.query

    run_async(scenario())


def test_first_frame_sets_generation_and_cursor():
    async def scenario():
        async with fake_switch() as (fake, server):
            fake.next_sequence = 8
            conn = make_conn(server)
            async with running(conn):
                assert conn.generation == 1
                assert conn.cursor == 7

    run_async(scenario())


def test_pong_within_200ms_even_while_worker_thread_sleeps():
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            async with running(conn):
                rec = fake.connections[0]
                t0 = time.monotonic()
                asyncio.get_running_loop().run_in_executor(None, time.sleep, 1.0)
                await asyncio.sleep(1.0)
                pings = [p for p in rec.pings_sent if p >= t0]
                assert len(pings) >= 4
                for ping in pings[:-1]:
                    assert any(ping <= t <= ping + 0.2 for t, _ in rec.pongs), ping

    run_async(scenario())


def test_pong_cursor_is_highest_sequence():
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            async with running(conn):
                seqs = [await fake.inject("agent-cr", msg(fake, f"m{i}", f"id{i}")) for i in (1, 2, 3)]
                await asyncio.sleep(0.5)
                assert fake.connections[0].pongs[-1][1] == seqs[2]

    run_async(scenario())


def test_events_delivered_in_order_and_duplicates_skipped():
    async def scenario():
        async with fake_switch() as (fake, server):
            received: list = []
            conn = make_conn(server, received=received)
            async with running(conn):
                s1 = await fake.inject("agent-cr", msg(fake, "m1", "id1"))
                s2 = await fake.inject("agent-cr", msg(fake, "m2", "id2"))
                await fake.send_raw("agent-cr", fake.buffers["agent-cr"][0])
                s3 = await fake.inject("agent-cr", msg(fake, "m3", "id3"))
                await asyncio.sleep(0.3)
                assert [frames.sequence_of(f) for _, f in received] == [s1, s2, s3]
                assert {a for a, _ in received} == {"carbon-room"}

    run_async(scenario())


def test_server_drop_reconnects_with_same_id_and_cursor_no_loss():
    async def scenario():
        async with fake_switch() as (fake, server):
            received: list = []
            conn = make_conn(server, received=received)
            async with running(conn):
                first = [await fake.inject("agent-cr", msg(fake, f"m{i}", f"id{i}")) for i in (1, 2, 3)]
                await asyncio.sleep(0.1)
                await fake.drop("agent-cr", 1012)
                more = [await fake.inject("agent-cr", msg(fake, f"m{i}", f"id{i}")) for i in (4, 5)]
                await fake.wait_for_connections("agent-cr", 2)
                await asyncio.sleep(0.3)
                assert [frames.sequence_of(f) for _, f in received] == first + more
                q0, q1 = fake.connections[0].query, fake.connections[1].query
                assert q1["connection_id"] == q0["connection_id"]
                assert q1["start_from"] == str(first[2])
                assert q1["expected_generation"] == "1"
                assert DELAYS == [1]

    run_async(scenario())


def test_evicted_heartbeat_reconnects(caplog):
    caplog.set_level(logging.WARNING)

    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            async with running(conn):
                await fake.evict("agent-cr", "heartbeat_lapsed")
                await fake.wait_for_connections("agent-cr", 2)

    run_async(scenario())
    assert "heartbeat_lapsed" in caplog.text


def test_server_evicts_when_client_never_pongs():
    async def scenario():
        async with fake_switch(ping_interval=0.1, evict_after=0.3) as (fake, server):
            path = "/agents/agent-x/connection/ws?connection_id=c&rooms=room-1&filter=all"
            uri = server.replace("http://", "ws://") + path
            seen: list[dict] = []
            code = None
            async with connect(uri, additional_headers={"Authorization": "Bearer k"}, ping_interval=None) as ws:
                try:
                    while True:
                        seen.append(json.loads(await ws.recv()))
                except ConnectionClosed as exc:
                    code = exc.rcvd.code
            kinds = [f["type"] for f in seen]
            assert kinds[0] == "connection_state"
            assert "ping" in kinds
            assert kinds[-1] == "evicted"
            assert seen[-1]["code"] == "heartbeat_lapsed"
            assert code == 1000

    run_async(asyncio.wait_for(scenario(), 1.5))


@pytest.mark.parametrize("code", ["taken_over", "closed"])
def test_evicted_final_codes_stop(code):
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            task = asyncio.create_task(conn.run())
            await asyncio.wait_for(conn.connected.wait(), 2)
            await fake.evict("agent-cr", code)
            await asyncio.wait_for(task, 1)
            assert task.exception() is None
            assert len([r for r in fake.connections if r.agent_id == "agent-cr"]) == 1

    run_async(scenario())


def test_4401_raises_auth_error_without_retry():
    async def scenario():
        async with fake_switch(api_keys={"agent-cr": "right"}) as (fake, server):
            conn = make_conn(server, key="wrong")
            with pytest.raises(AuthError):
                await conn.run()
            assert len(fake.connections) == 1
            assert DELAYS == []

    run_async(scenario())


def test_4403_stops_without_retry(caplog):
    caplog.set_level(logging.WARNING)

    async def scenario():
        async with fake_switch() as (fake, server):
            fake.refuse_next("agent-cr", 4403)
            conn = make_conn(server)
            assert await asyncio.wait_for(conn.run(), 1) is None
            assert len(fake.connections) == 1

    run_async(scenario())
    assert any(r.levelno == logging.ERROR and "4403" in r.getMessage() for r in caplog.records)


def test_gap_frame_moves_cursor():
    async def scenario():
        async with fake_switch() as (fake, server):
            received: list = []
            conn = make_conn(server, received=received)
            async with running(conn):
                fake.next_sequence = 50
                await fake.send_raw(
                    "agent-cr",
                    {
                        "type": "gap", "from_sequence": 3, "resumed_at": 50, "resumed_position": 0,
                        "rooms": ["room-1"], "all_rooms": False, "reason": "retention",
                    },
                )
                await asyncio.sleep(0.1)
                seq = await fake.inject("agent-cr", msg(fake, "after gap", "id-gap"))
                await asyncio.sleep(0.2)
                assert seq == 50
                assert conn.cursor == 50
                assert [frames.sequence_of(f) for _, f in received] == [50]

    run_async(scenario())


@pytest.mark.parametrize("style", ["type", "event"])
def test_both_control_styles(style):
    async def scenario():
        async with fake_switch(control_style=style) as (fake, server):
            received: list = []
            conn = make_conn(server, received=received)
            async with running(conn):
                assert conn.connected.is_set()
                await fake.inject("agent-cr", msg(fake, "hello", "id1"))
                await asyncio.sleep(0.5)
                assert len(received) == 1
                assert fake.connections[0].pongs

    run_async(scenario())


def test_first_frame_not_state_reconnects(caplog):
    caplog.set_level(logging.WARNING)
    count = [0]

    async def handler(ws):
        count[0] += 1
        if count[0] == 1:
            await ws.send(json.dumps({"type": "ping"}))
        else:
            await ws.send(json.dumps({"type": "connection_state", "generation": 1, "cursor": 0}))
        try:
            await ws.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    async def scenario():
        quiet = logging.getLogger("test.quiet")
        quiet.setLevel(logging.ERROR)
        async with serve(handler, "127.0.0.1", 0, logger=quiet) as srv:
            port = srv.sockets[0].getsockname()[1]
            conn = make_conn(f"http://127.0.0.1:{port}")
            async with running(conn):
                assert count[0] == 2

    run_async(scenario())
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_on_event_exception_is_logged_and_loop_continues(caplog):
    caplog.set_level(logging.WARNING)
    got: list = []

    def on_event(agent, frame):
        if not got:
            got.append("boom")
            raise RuntimeError("handler exploded")
        got.append(frames.sequence_of(frame))

    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server, on_event=on_event)
            async with running(conn):
                await fake.inject("agent-cr", msg(fake, "a", "id1"))
                s2 = await fake.inject("agent-cr", msg(fake, "b", "id2"))
                await asyncio.sleep(0.3)
                assert got == ["boom", s2]
                assert conn.connected.is_set()

    run_async(scenario())
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_backoff_sequence():
    assert list(itertools.islice(backoff_delays(), 8)) == [1, 2, 4, 8, 16, 30, 30, 30]


def test_backoff_resets_after_connect():
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            async with running(conn):
                await fake.drop("agent-cr")
                await fake.wait_for_connections("agent-cr", 2)
                await asyncio.wait_for(conn.connected.wait(), 2)
                await fake.drop("agent-cr")
                await fake.wait_for_connections("agent-cr", 3)
                assert DELAYS == [1, 1]

    run_async(scenario())


def test_stop_returns_quickly():
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            task = asyncio.create_task(conn.run())
            await asyncio.wait_for(conn.connected.wait(), 2)
            t0 = time.monotonic()
            await conn.stop()
            await task
            assert time.monotonic() - t0 < 1.0

    run_async(scenario())


def test_stop_during_backoff():
    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server, sleep=asyncio.sleep)
            task = asyncio.create_task(conn.run())
            await asyncio.wait_for(conn.connected.wait(), 2)
            await fake.stop()
            await asyncio.sleep(0.3)
            t0 = time.monotonic()
            await conn.stop()
            await asyncio.wait_for(task, 1)
            assert time.monotonic() - t0 < 1.0

    run_async(scenario())


def test_stop_before_run_returns_at_once():
    async def scenario():
        conn = make_conn("http://127.0.0.1:9")
        await conn.stop()
        await asyncio.wait_for(conn.run(), 1)

    run_async(scenario())


def test_key_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    holder: dict = {}

    async def scenario():
        async with fake_switch() as (fake, server):
            conn = make_conn(server)
            holder["conn"] = conn
            async with running(conn):
                await fake.inject("agent-cr", msg(fake, "x", "id1"))
                await fake.drop("agent-cr")
                await fake.wait_for_connections("agent-cr", 2)
                await asyncio.sleep(0.1)
        async with fake_switch(api_keys={"agent-cr": "right"}) as (fake, server):
            bad = make_conn(server)
            try:
                await bad.run()
            except AuthError as exc:
                holder["err"] = str(exc)

    run_async(scenario())
    assert "err" in holder
    assert KEY not in caplog.text
    assert KEY not in repr(holder["conn"])
    assert KEY not in holder["err"]
