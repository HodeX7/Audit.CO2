"""Turn an uploaded file into a managed regular file under the inbox."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from carbon_room.room.events import Attachment

MAX_BYTES: int = 10 * 1024 * 1024
MAX_NAME: int = 150


class AttachmentMissing(Exception):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


def safe_name(name: str) -> str:
    raise NotImplementedError


async def fetch(
    *,
    message_id: str,
    attachment: Attachment | None,
    typed_name: str | None,
    mode: str,
    inbox_dir: Path,
    download: Callable[[Attachment], Awaitable[bytes]] | None,
) -> Path:
    raise NotImplementedError
