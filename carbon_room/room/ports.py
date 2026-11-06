"""Room port and shared handler context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

AGENT_NAMES: tuple[str, ...] = ("carbon-room", "collector", "watchdog", "reporter")
AGENT_TITLES: dict[str, str] = {
    "carbon-room": "Carbon Room",
    "collector": "Collector",
    "watchdog": "Watchdog",
    "reporter": "Reporter",
}


@runtime_checkable
class Room(Protocol):
    async def post(
        self, agent: str, text: str, *, thread_id: str | None = None, essential: bool = True
    ) -> str: ...

    async def send_targeted(self, from_agent: str, to_agent: str, text: str) -> None: ...

    async def upsert_doc(self, agent: str, name: str, content: str) -> bool: ...

    def link(self, message_id: str) -> str: ...

    def begin_close(self, close_id: str) -> None: ...


async def noop_phase_end(close_id: str) -> None:
    raise NotImplementedError


def utc_today() -> date:
    raise NotImplementedError


@dataclass
class Context:
    core: Any
    room: Room
    display: Callable[[str], str] = str
    today: Callable[[], date] = utc_today
    on_phase_end: Callable[[str], Awaitable[None]] = noop_phase_end
    threads: bool = True
    attachments_mode: str = "inbox"
    inbox_dir: Path = Path("data/inbox")
    download: Callable[[Any], Awaitable[bytes]] | None = None
    out_dir: Path = Path("out")
    state: dict = field(default_factory=dict)
