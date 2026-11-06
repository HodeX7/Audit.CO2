"""Dispatcher: decode, dedupe, classify and run Switch events in lanes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent

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
        raise NotImplementedError

    def submit(self, agent_name: str, frame: dict) -> None:
        raise NotImplementedError

    async def run(self) -> None:
        raise NotImplementedError

    async def join(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError
