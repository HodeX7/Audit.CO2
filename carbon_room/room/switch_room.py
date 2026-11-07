"""Switch operations-backed implementation of the room port."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from carbon_room.room.ports import AGENT_TITLES

log = logging.getLogger(__name__)


class SwitchRoom:
    def __init__(self, clients: Mapping[str, Any], *, single_agent: bool = False,
                 permalink_base: str | None = None, threads: bool = True) -> None:
        self.clients = clients
        self.single_agent = single_agent
        self.permalink_base = permalink_base.rstrip("/") if permalink_base else None
        self.threads = threads

    def _client(self, agent: str) -> Any:
        return self.clients["carbon-room" if self.single_agent else agent]

    async def post(self, agent: str, text: str, *, thread_id: str | None = None,
                   essential: bool = True) -> str:
        if thread_id and not self.threads:
            log.info("threads off: posting reply to %s at top level", thread_id)
            text = "↳ " + text
            thread_id = None
        if self.single_agent and agent != "carbon-room":
            text = f"[{AGENT_TITLES[agent]}] {text}"
        return await self._client(agent).post(text, thread_id)

    async def send_targeted(self, from_agent: str, to_agent: str, text: str) -> None:
        if self.single_agent:
            log.info("single-agent mode: skipping handoff from %s to %s", from_agent, to_agent)
            return
        await self._client(from_agent).send_targeted(to_agent, text)

    async def upsert_doc(self, agent: str, name: str, content: str) -> bool:
        return await self._client(agent).upsert_room_doc(name, content)

    def link(self, message_id: str) -> str:
        return (f"{self.permalink_base}/{message_id}" if self.permalink_base
                else f"message {message_id}")

    def begin_close(self, close_id: str) -> None:
        log.debug("begin close %s", close_id)
