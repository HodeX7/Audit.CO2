"""Top-level post budget for a close."""

from __future__ import annotations

import logging

from carbon_room import config
from carbon_room.room.ports import Room

log = logging.getLogger(__name__)

DEFAULT_MAX_POSTS = 12


class NoiseGuard:
    """Wraps a Room; merges non-essential top-level posts into the next essential one."""

    def __init__(self, inner: Room, *, max_posts: int = DEFAULT_MAX_POSTS, reserve: int = 2) -> None:
        self._inner = inner
        self._max = max_posts
        self._reserve = reserve
        self.top_level_count: int = 0
        self.buffered: list[str] = []

    async def post(self, agent, text, *, thread_id=None, essential=True) -> str:
        if thread_id is not None:
            return await self._inner.post(agent, text, thread_id=thread_id, essential=essential)
        if not essential and self.top_level_count >= self._max - self._reserve:
            self.buffered.append(text)
            log.warning("noise guard merged a post into the next one")
            return ""
        if essential and self.buffered:
            text = "\n".join(self.buffered) + "\n\n" + text
            self.buffered = []
        message_id = await self._inner.post(agent, text, thread_id=None, essential=essential)
        self.top_level_count += 1
        if self.top_level_count > self._max:
            log.warning("top-level posts for this close: %d (limit %d)", self.top_level_count, self._max)
        return message_id

    async def send_targeted(self, from_agent, to_agent, text) -> None:
        await self._inner.send_targeted(from_agent, to_agent, text)

    async def upsert_doc(self, agent, name, content) -> bool:
        return await self._inner.upsert_doc(agent, name, content)

    def link(self, message_id: str) -> str:
        return self._inner.link(message_id)

    def begin_close(self, close_id: str) -> None:
        self.top_level_count = 0
        self.buffered = []
        self._inner.begin_close(close_id)


def max_posts_from_config() -> int:
    try:
        settings = config.load_config()
    except FileNotFoundError:
        return DEFAULT_MAX_POSTS
    return int((settings.get("noise") or {}).get("max_top_level_posts", DEFAULT_MAX_POSTS))
