"""One Switch WebSocket per agent (stub; implemented in the green commit)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from typing import Literal

WIRE_LOG = logging.getLogger("carbon_room.room.connection.wire")
WIRE_LOG.setLevel(logging.WARNING)


class AuthError(Exception):
    pass


def backoff_delays() -> Iterator[float]:
    raise NotImplementedError


class AgentConnection:
    agent_name: str
    connection_id: str
    cursor: int | None
    generation: int | None
    connected: asyncio.Event

    def __init__(
        self,
        agent_name: str,
        agent_id: str,
        api_key: str,
        server: str,
        room_ids: list[str],
        filter: Literal["all", "addressed"],
        on_event: Callable[[str, dict], None],
        *,
        connection_id: str | None = None,
        client_version: str = "0.1.0",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        raise NotImplementedError

    def url(self) -> str:
        raise NotImplementedError

    async def run(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError
