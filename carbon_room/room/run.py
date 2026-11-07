"""One-process Switch runtime: four sockets, one dispatcher, one authoritative core."""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import signal
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from carbon_room.agents import hooks, orchestrator
from carbon_room.room import app, events, identity
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.connection import AgentConnection
from carbon_room.room.dispatch import Dispatcher
from carbon_room.room.noise import NoiseGuard, max_posts_from_config
from carbon_room.room.ops import OpsClient
from carbon_room.room.ports import AGENT_NAMES, Context
from carbon_room.room.settings import Settings, load_settings
from carbon_room.room.switch_room import SwitchRoom

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    ctx: Context
    dispatcher: Dispatcher
    connections: dict[str, AgentConnection]
    clients: dict[str, OpsClient]
    executor: concurrent.futures.ThreadPoolExecutor
    tasks: list[asyncio.Task] = field(default_factory=list)

    async def start(self) -> None:
        if self.tasks:
            raise RuntimeError("runtime already started")
        self.tasks = [asyncio.create_task(self.dispatcher.run(), name="room-dispatcher")]
        self.tasks.extend(asyncio.create_task(c.run(), name=f"socket-{name}")
                          for name, c in self.connections.items())

    async def wait_connected(self, timeout: float) -> list[str]:
        async def wait_one(name: str, connection: AgentConnection, task: asyncio.Task) -> str | None:
            connected = asyncio.create_task(connection.connected.wait())
            try:
                done, _ = await asyncio.wait({connected, task}, timeout=timeout,
                                             return_when=asyncio.FIRST_COMPLETED)
                return None if connected in done and connection.connected.is_set() else name
            finally:
                connected.cancel()

        return [name for name in await asyncio.gather(*(
            wait_one(name, connection, self.tasks[i + 1])
            for i, (name, connection) in enumerate(self.connections.items())
        )) if name is not None]

    async def stop(self) -> None:
        for connection in self.connections.values():
            await connection.stop()
        await self.dispatcher.stop()
        await asyncio.gather(*(client.aclose() for client in self.clients.values()),
                             return_exceptions=True)
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.tasks:
            results = await asyncio.gather(*self.tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                    log.error("runtime task stopped with %s: %s", type(result).__name__, result)
            self.tasks.clear()


def build(settings: Settings, *, core: Any,
          transport: httpx.AsyncBaseTransport | None = None) -> Runtime:
    names = ("carbon-room",) if settings.single_agent else AGENT_NAMES
    ids = {name: creds.agent_id for name, creds in settings.agents.items()}
    clients: dict[str, OpsClient] = {}
    connections: dict[str, AgentConnection] = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="core")
    room = NoiseGuard(SwitchRoom(clients, single_agent=settings.single_agent,
                                 permalink_base=settings.permalink_base, threads=settings.threads),
                      max_posts=max_posts_from_config())
    watcher = "carbon-room" if settings.single_agent else "watchdog"
    download = None
    if settings.attachments_mode == "download" and settings.media_path:
        async def download(attachment: Any) -> bytes:
            return await clients[watcher].download(attachment.mxc, settings.media_path)

    ctx = Context(core=AsyncCore(core, executor), room=room, display=identity.display,
                  threads=settings.threads, attachments_mode=settings.attachments_mode,
                  inbox_dir=settings.inbox_dir, download=download)
    ctx.on_phase_end = functools.partial(hooks.after_phase, ctx)
    own_ids = frozenset(ids.values())
    dispatcher = Dispatcher(decode=lambda name, frame: events.decode(frame, name, own_ids),
                            classify=lambda event: app.classify(event, today=ctx.today(),
                                                                single_agent=settings.single_agent),
                            handle=lambda event, intent: app.handle(ctx, event, intent),
                            on_error=lambda event, intent, exc: app.on_error(ctx, event, intent, exc),
                            room_id=settings.room_id)
    for name in names:
        creds = settings.agents[name]
        connection_id = str(uuid.uuid4())
        clients[name] = OpsClient(settings.server, creds.agent_id, creds.api_key,
                                  connection_id=connection_id, room_id=settings.room_id,
                                  transport=transport, agent_ids=ids)
        connections[name] = AgentConnection(
            name, creds.agent_id, creds.api_key, settings.server, [settings.room_id],
            "all" if name == "watchdog" or settings.single_agent else "addressed",
            dispatcher.submit, connection_id=connection_id,
        )
    return Runtime(ctx, dispatcher, connections, clients, executor)


async def amain(settings: Settings, *, core: Any = None,
                transport: httpx.AsyncBaseTransport | None = None,
                connect_timeout: float = 30.0,
                stop_event: asyncio.Event | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if core is None:
        from carbon_room import core as real_core
        from carbon_room.calc import factors

        factors.prepare_ledger()
        core = real_core
    runtime = build(settings, core=core, transport=transport)
    try:
        await runtime.start()
        failed = await runtime.wait_connected(connect_timeout)
        if failed:
            log.error("could not connect: %s; run make doctor", ", ".join(failed))
            return 2
        try:
            await orchestrator.resume_on_startup(runtime.ctx)
        except Exception:
            log.exception("startup resume failed")
        if stop_event is None:
            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                except NotImplementedError:
                    pass
        await stop_event.wait()
        log.info("stopped")
        return 0
    finally:
        await runtime.stop()


def main() -> int:
    if any(name in ("fakes", "tests") or name.startswith(("fakes.", "tests."))
           for name in sys.modules):
        print("refusing to run with test doubles loaded", file=sys.stderr)
        return 3
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"carbon-room: {exc}", file=sys.stderr)
        return 1
    return asyncio.run(amain(settings))


if __name__ == "__main__":
    raise SystemExit(main())
