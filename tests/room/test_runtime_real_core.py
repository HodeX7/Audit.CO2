"""Full offline socket-to-SQLite close, including publication and provenance."""

import asyncio
import json
import shutil
from pathlib import Path

import httpx
from fakes.fake_switch import FakeSwitch

from carbon_room import config, core
from carbon_room.calc import factors
from carbon_room.room.ports import AGENT_NAMES
from carbon_room.room.run import build
from carbon_room.room.settings import AgentCreds, Settings

ROOT = Path(__file__).resolve().parents[2]


async def wait_for(predicate, timeout=8):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(poll(), timeout)


def test_socket_to_real_core_publish(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copy(ROOT / "tests/room/fixtures/people.yaml", tmp_path / "config/people.yaml")
    shutil.copytree(ROOT / "data/seed", tmp_path / "data/seed")
    shutil.copytree(ROOT / "data/demo_uploads", tmp_path / "data/demo_uploads")
    inbox = tmp_path / "data/inbox"
    inbox.mkdir()
    shutil.copy(tmp_path / "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf", inbox)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(tmp_path / "config"))
    config.clear_caches()
    factors.prepare_ledger()

    async def scenario():
        switch = FakeSwitch(ping_interval=0.5, evict_after=5)
        server = await switch.start()
        calls = []

        def respond(request):
            op = request.url.path.rsplit("/", 1)[-1]
            body = json.loads(request.content) if request.content else {}
            agent = request.url.path.split("/")[2]
            calls.append((agent, op, body))
            if op == "post_message":
                result = {"event_id": f"srv-{len(calls)}"}
            elif op == "create_room_document":
                result = {"document_id": "board-1"}
            else:
                result = {}
            return httpx.Response(200, json={"result": result})

        settings = Settings(server, "room-1", {
            name: AgentCreds(name, f"agent-{name}", f"key-{name}") for name in AGENT_NAMES
        }, True, "inbox", False, None, None, inbox)
        runtime = build(settings, core=core, transport=httpx.MockTransport(respond))

        def posted(prefix):
            return [(f"srv-{i}", body) for i, (_, op, body) in enumerate(calls, 1)
                    if op == "post_message" and body.get("body", "").startswith(prefix)]

        async def send(agent, text, mid, *, thread=None, sender="@switch-user-lead:test"):
            payload = FakeSwitch.message(body=text, message_id=mid, thread_id=thread,
                                         sender=sender, sender_name="lead" if "lead" in sender else "priya")
            await switch.inject(f"agent-{agent}", payload)

        try:
            await runtime.start()
            assert await runtime.wait_connected(3) == []
            await send("carbon-room", "@carbon-room close 2026-10", "h-close")
            await wait_for(lambda: len(posted("**G-")) == 4)
            roots = {body["body"].split("· ", 1)[1].split("**", 1)[0]: mid
                     for mid, body in posted("**G-")}
            assert set(roots) == {"CONFLICTING", "STALE", "PERIOD", "VARIANCE"}
            for kind, text, mid, sender in (
                ("PERIOD", "upload warehouse2_electricity_2026-10_actual.pdf", "h-upload",
                 "@switch-user-priya:test"),
                ("CONFLICTING", "pick A", "h-pick", "@switch-user-lead:test"),
                ("STALE", "approve", "h-stale", "@switch-user-lead:test"),
                ("VARIANCE", "approve", "h-variance", "@switch-user-lead:test"),
            ):
                await send("watchdog", text, mid, thread=roots[kind], sender=sender)
                try:
                    await wait_for(lambda root=roots[kind]: any(
                        op == "post_message" and body.get("thread_id") == root and
                        body.get("body", "").startswith("Resolved.") for _, op, body in calls))
                except TimeoutError:
                    raise AssertionError((kind, [body for _, op, body in calls
                                                   if op == "post_message"][-12:])) from None
            assert (await runtime.ctx.core.summary("2026-10-v1")).sources_verified == 4
            await send("reporter", "@reporter draft", "h-draft")
            await wait_for(lambda: any(op == "post_message" and "**Draft v1" in body.get("body", "")
                                       for _, op, body in calls))
            await send("carbon-room", "@carbon-room publish", "h-publish")
            await wait_for(lambda: bool(posted("Published v1")))
            assert (await runtime.ctx.core.resume_state("2026-10-v1"))[0] == "PUBLISHED"
            assert (await runtime.ctx.core.verify_audit("2026-10-v1")).ok
            assert (tmp_path / "out/2026-10/v1/report.pdf").is_file()
        finally:
            await runtime.stop()
            await switch.stop()

    try:
        asyncio.run(asyncio.wait_for(scenario(), 20))
    finally:
        config.clear_caches()
