"""Dispatcher: decode, dedupe, classify and run Switch events in lanes."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

log = logging.getLogger(__name__)

MUTATING_KINDS: frozenset[str] = frozenset(
    {"close.start", "close.resume", "close.publish", "report.draft", "gap.reply", "gap.fallback"}
)


class Dispatcher:
    handled_count: int

    def __init__(
        self,
        *,
        decode: Callable[[str, dict], RoomEvent | None],
        classify: Callable[[RoomEvent], Intent],
        handle: Callable[[RoomEvent, Intent], Awaitable[None]],
        on_error: Callable[[RoomEvent, Intent, BaseException], Awaitable[None]],
        room_id: str,
        max_reads: int = 4,
        seen_limit: int = 5000,
    ) -> None:
        self._decode = decode
        self._classify = classify
        self._handle = handle
        self._on_error = on_error
        self._room_id = room_id
        self._seen_limit = seen_limit
        self._max_reads = max_reads
        self._intake: asyncio.Queue = asyncio.Queue()
        self._mutations: asyncio.Queue = asyncio.Queue()
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._reads: set[asyncio.Task] = set()
        self._read_slots: asyncio.Semaphore | None = None
        self._worker: asyncio.Task | None = None
        self._stopping = False
        self._stop_event = asyncio.Event()
        self.handled_count = 0

    def submit(self, agent_name: str, frame: dict) -> None:
        if self._stopping:
            log.debug("dispatcher stopped; ignoring frame from %s", agent_name)
            return
        self._intake.put_nowait((agent_name, frame))

    async def run(self) -> None:
        self._read_slots = asyncio.Semaphore(self._max_reads)
        self._worker = asyncio.create_task(self._mutation_worker())
        stop_wait = asyncio.create_task(self._stop_event.wait())
        try:
            while not self._stopping:
                getter = asyncio.create_task(self._intake.get())
                await asyncio.wait({getter, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
                if not getter.done():
                    getter.cancel()
                    break
                try:
                    agent_name, frame = getter.result()
                    try:
                        self._process(agent_name, frame)
                    except Exception:
                        log.exception("dispatcher intake failed")
                finally:
                    self._intake.task_done()
        finally:
            stop_wait.cancel()

    def _process(self, agent_name: str, frame: dict) -> None:
        try:
            event = self._decode(agent_name, frame)
        except Exception:
            log.warning("could not decode frame from %s", agent_name, exc_info=True)
            return
        if event is None or event.type != "message":
            return
        if event.room_id != self._room_id:
            log.debug("dropping message %s from another room", event.message_id)
            return
        if event.message_id in self._seen:
            log.debug("dropping already handled message %s", event.message_id)
            return
        try:
            intent = self._classify(event)
        except Exception:
            log.warning("could not classify message %s", event.message_id, exc_info=True)
            return
        if intent.kind == "ignore":
            return
        self._seen[event.message_id] = None
        while len(self._seen) > self._seen_limit:
            self._seen.popitem(last=False)
        self.handled_count += 1
        if intent.kind in MUTATING_KINDS:
            self._mutations.put_nowait((event, intent))
        else:
            task = asyncio.create_task(self._read(event, intent))
            self._reads.add(task)
            task.add_done_callback(self._reads.discard)

    async def _invoke(self, event: RoomEvent, intent: Intent) -> None:
        try:
            await self._handle(event, intent)
        except Exception as exc:
            try:
                await self._on_error(event, intent, exc)
            except Exception:
                log.exception("on_error failed for message %s", event.message_id)

    async def _read(self, event: RoomEvent, intent: Intent) -> None:
        assert self._read_slots is not None
        async with self._read_slots:
            await self._invoke(event, intent)

    async def _mutation_worker(self) -> None:
        while True:
            item = await self._mutations.get()
            try:
                if item is None:
                    return
                await self._invoke(*item)
            finally:
                self._mutations.task_done()

    async def join(self) -> None:
        while True:
            await self._intake.join()
            await self._mutations.join()
            if self._reads:
                await asyncio.wait(set(self._reads))
            if (self._intake.empty() and self._mutations.empty() and not self._reads
                    and self._intake._unfinished_tasks == 0  # type: ignore[attr-defined]
                    and self._mutations._unfinished_tasks == 0):  # type: ignore[attr-defined]
                return

    async def stop(self) -> None:
        self._stopping = True
        self._stop_event.set()
        dropped = 0
        while True:
            try:
                item = self._mutations.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._mutations.task_done()
            if item is not None:
                dropped += 1
        if dropped:
            log.warning("dropping %d queued mutation(s) on stop", dropped)
        if self._worker is not None:
            self._mutations.put_nowait(None)
            await asyncio.wait({self._worker})
        reads = list(self._reads)
        for task in reads:
            task.cancel()
        if reads:
            await asyncio.gather(*reads, return_exceptions=True)
        self._reads.clear()
        await asyncio.sleep(0)
