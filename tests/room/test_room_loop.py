"""Exercise the complete socket → dispatcher → core → ops loop without live Switch."""

import asyncio
import json

import httpx
from fakes.fake_core import FakeCore
from fakes.fake_switch import FakeSwitch

from carbon_room.room.ports import AGENT_NAMES
from carbon_room.room.settings import AgentCreds, Settings


async def wait_until(predicate, timeout=10):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(poll(), timeout)


def make_settings(server):
    return Settings(server=server, room_id="room-1",
                    agents={name: AgentCreds(name, f"agent-{name}", f"key-{name}")
                            for name in AGENT_NAMES},
                    threads=True, attachments_mode="inbox", single_agent=False,
                    permalink_base=None, media_path=None)


def test_close_and_thread_reply_over_fake_switch(people_config):
    from carbon_room.room.run import build

    async def scenario():
        switch = FakeSwitch(ping_interval=0.5, evict_after=5)
        server = await switch.start()
        calls = []

        def respond(request):
            op = request.url.path.rsplit("/", 1)[-1]
            agent = request.url.path.split("/")[2]
            body = json.loads(request.content) if request.content else {}
            calls.append((agent, op, body))
            result = {"event_id": f"srv-{len(calls)}"} if op == "post_message" else {}
            return httpx.Response(200, json={"result": result})

        core = FakeCore()
        runtime = build(make_settings(server), core=core, transport=httpx.MockTransport(respond))
        try:
            await runtime.start()
            assert await runtime.wait_connected(5) == []
            first = FakeSwitch.message(body="@carbon-room close October", message_id="h-1")
            await switch.inject("agent-carbon-room", first)
            await switch.inject("agent-watchdog", dict(first, addressed=False))
            await wait_until(lambda: any(op == "post_message" and
                                         body.get("body", "").startswith("I can't give a clean October")
                                         for _, op, body in calls))
            roots = [(f"srv-{i}", body) for i, (_, op, body) in enumerate(calls, 1)
                     if op == "post_message" and body.get("body", "").startswith("**G-2 ")]
            assert len(roots) == 1
            root = roots[0][0]
            await switch.inject("agent-watchdog", FakeSwitch.message(
                body="pick A", message_id="h-2", thread_id=root))
            await wait_until(lambda: any(op == "post_message" and
                                         body.get("body") == "Resolved. G-2 is closed and the ledger is updated."
                                         for _, op, body in calls))
            starts = [args for name, args in core.calls if name == "start_close"]
            resolves = [args for name, args in core.calls if name == "resolve"]
            assert len(starts) == len(resolves) == 1
            assert starts[0]["chat_message_id"] == "h-1"
            assert resolves[0]["chat_message_id"] == "h-2"
            assert resolves[0]["gap_id"] == "G-2"
            assert resolves[0]["action"] == "pick"
            assert resolves[0]["payload"] == {"claim_id": "CL-0003"}
            assert resolves[0]["actor"].id == "lead"
            assert any(agent == "agent-watchdog" and op == "post_message" and
                       body.get("thread_id") == root and body.get("body", "").startswith("Resolved.")
                       for agent, op, body in calls)
        finally:
            await runtime.stop()
            await switch.stop()

    asyncio.run(asyncio.wait_for(scenario(), 20))


def test_amain_returns_connect_error_on_bad_agent_key(people_config):
    from carbon_room.room.run import amain

    async def scenario():
        switch = FakeSwitch(api_keys={"agent-carbon-room": "different"})
        server = await switch.start()
        try:
            result = await amain(make_settings(server), core=FakeCore(),
                                 connect_timeout=1, stop_event=asyncio.Event())
            assert result == 2
        finally:
            await switch.stop()

    asyncio.run(asyncio.wait_for(scenario(), 5))


def test_amain_stops_on_event(people_config):
    from carbon_room.room.run import amain

    async def scenario():
        switch = FakeSwitch()
        server = await switch.start()
        stop = asyncio.Event()
        task = asyncio.create_task(amain(make_settings(server), core=FakeCore(),
                                         connect_timeout=3, stop_event=stop))
        try:
            await wait_until(lambda: len(switch.connections) == 4, timeout=3)
            stop.set()
            assert await asyncio.wait_for(task, 3) == 0
        finally:
            if not task.done():
                task.cancel()
            await switch.stop()

    asyncio.run(asyncio.wait_for(scenario(), 7))


def test_amain_bootstraps_real_core_before_connect(tmp_path, monkeypatch):
    from pathlib import Path

    from carbon_room import config
    from carbon_room.ledger import connect
    from carbon_room.room.run import amain

    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(root / "config"))
    config.clear_caches()

    async def scenario():
        switch = FakeSwitch()
        server = await switch.start()
        stop = asyncio.Event()
        stop.set()
        try:
            assert await amain(make_settings(server), stop_event=stop, connect_timeout=3) == 0
        finally:
            await switch.stop()

    try:
        asyncio.run(asyncio.wait_for(scenario(), 6))
        with connect(tmp_path / "var/carbon_room.db") as db:
            assert db.execute("SELECT COUNT(*) FROM factors").fetchone()[0] > 0
    finally:
        config.clear_caches()
