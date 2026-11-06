"""Top-level post budget for a close."""

from __future__ import annotations

from carbon_room.room.ports import Room


class NoiseGuard:
    top_level_count: int
    buffered: list[str]

    def __init__(self, inner: Room, *, max_posts: int = 12, reserve: int = 2) -> None:
        raise NotImplementedError

    async def post(self, agent, text, *, thread_id=None, essential=True) -> str:
        raise NotImplementedError

    async def send_targeted(self, from_agent, to_agent, text) -> None:
        raise NotImplementedError

    async def upsert_doc(self, agent, name, content) -> bool:
        raise NotImplementedError

    def link(self, message_id: str) -> str:
        raise NotImplementedError

    def begin_close(self, close_id: str) -> None:
        raise NotImplementedError


def max_posts_from_config() -> int:
    raise NotImplementedError
