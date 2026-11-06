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
    """Satisfies ``carbon_room.room.ports.Room`` and records everything."""

    def __init__(self, *, supports_docs: bool = True) -> None:
        self.supports_docs = supports_docs
        self.posts: list[Post] = []
        self.targeted: list[tuple[str, str, str]] = []
        self.docs: dict[str, str] = {}
        self.closes: list[str] = []

    async def post(self, agent, text, *, thread_id=None, essential=True) -> str:
        message_id = f"m-{len(self.posts) + 1}"
        self.posts.append(Post(agent, text, thread_id, essential, message_id))
        return message_id

    async def send_targeted(self, from_agent, to_agent, text) -> None:
        self.targeted.append((from_agent, to_agent, text))

    async def upsert_doc(self, agent, name, content) -> bool:
        if not self.supports_docs:
            return False
        self.docs[name] = content
        return True

    def link(self, message_id: str) -> str:
        return f"message {message_id}"

    def begin_close(self, close_id: str) -> None:
        self.closes.append(close_id)

    def top_level(self) -> list[Post]:
        return [p for p in self.posts if p.thread_id is None]

    def in_thread(self, thread_id: str) -> list[Post]:
        return [p for p in self.posts if p.thread_id == thread_id]
