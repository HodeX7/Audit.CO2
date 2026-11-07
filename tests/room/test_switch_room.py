"""The room adapter must preserve agent attribution and thread routing."""

import asyncio
import logging

from carbon_room.room.ports import Room


class Client:
    def __init__(self):
        self.posts = []
        self.targeted = []
        self.docs = []

    async def post(self, text, thread_id=None):
        self.posts.append((text, thread_id))
        return f"srv-{len(self.posts)}"

    async def send_targeted(self, agent, text):
        self.targeted.append((agent, text))

    async def upsert_room_doc(self, name, content):
        self.docs.append((name, content))
        return True


def test_agent_routing_and_targeted_ops():
    from carbon_room.room.switch_room import SwitchRoom

    async def check():
        clients = {name: Client() for name in ("carbon-room", "watchdog", "reporter")}
        room = SwitchRoom(clients)
        assert isinstance(room, Room)
        assert await room.post("watchdog", "gap", thread_id="m-1") == "srv-1"
        assert await room.post("reporter", "report") == "srv-1"
        await room.send_targeted("carbon-room", "collector", "go")
        assert await room.upsert_doc("carbon-room", "close-board", "md")
        assert clients["watchdog"].posts == [("gap", "m-1")]
        assert clients["reporter"].posts == [("report", None)]
        assert clients["carbon-room"].targeted == [("collector", "go")]
        assert clients["carbon-room"].docs == [("close-board", "md")]
        assert room.link("abc") == "message abc"

    asyncio.run(check())


def test_single_agent_and_thread_fallback(caplog):
    from carbon_room.room.switch_room import SwitchRoom

    caplog.set_level(logging.INFO)

    async def check():
        client = Client()
        room = SwitchRoom({"carbon-room": client}, single_agent=True, threads=False,
                          permalink_base="http://mm/team/pl/")
        await room.post("watchdog", "Checking…", thread_id="m-1")
        await room.post("carbon-room", "ready")
        await room.send_targeted("carbon-room", "collector", "go")
        assert client.posts == [("[Watchdog] ↳ Checking…", None), ("ready", None)]
        assert client.targeted == []
        assert room.link("abc") == "http://mm/team/pl/abc"

    asyncio.run(check())
    assert "threads off" in caplog.text
