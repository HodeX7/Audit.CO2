"""In-memory Room double."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Post:
    agent: str
    text: str
    thread_id: str | None
    essential: bool
    message_id: str


class FakeRoom:
    def __init__(self, *, supports_docs: bool = True) -> None:
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

    def top_level(self) -> list[Post]:
        raise NotImplementedError

    def in_thread(self, thread_id: str) -> list[Post]:
        raise NotImplementedError
