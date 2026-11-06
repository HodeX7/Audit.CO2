"""Turn an uploaded file into a managed regular file under the inbox."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from carbon_room.room.events import Attachment

log = logging.getLogger(__name__)

_BAD_CHAR = re.compile(r"[^A-Za-z0-9._-]")

MAX_BYTES: int = 10 * 1024 * 1024
MAX_NAME: int = 150


class AttachmentMissing(Exception):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


def _too_big() -> AttachmentMissing:
    return AttachmentMissing("That file is over 10 MiB, so I can't take it.")


def safe_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    clean = _BAD_CHAR.sub("_", base)
    if clean in ("", ".", "..") or clean.startswith("."):
        raise AttachmentMissing("That file name isn't usable. Rename it and try again.")
    if len(clean) > MAX_NAME:
        raise AttachmentMissing("That file name is too long. Rename it and try again.")
    return clean


def _write_new(inbox_dir: Path, target: Path, data: bytes) -> None:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "xb") as f:
            f.write(data)
    except FileExistsError:
        raise AttachmentMissing(
            f"I already have a file called {target.name}. Rename it and try again."
        ) from None


def _check_inbox_file(inbox_dir: Path, candidate: Path, safe: str) -> None:
    gone = AttachmentMissing(
        f"I can't see that file yet. Put it in {inbox_dir.as_posix()}/ and reply upload {safe}."
    )
    if candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
        raise gone
    if not candidate.resolve().is_relative_to(inbox_dir.resolve()):
        raise gone
    if candidate.stat().st_size > MAX_BYTES:
        raise _too_big()


async def _from_inbox(
    attachment: Attachment | None, typed_name: str | None, inbox_dir: Path
) -> Path:
    name = typed_name or (attachment.filename if attachment else None)
    if not name:
        raise AttachmentMissing(
            f"I can't see that file yet. Put it in {inbox_dir.as_posix()}/ and reply upload <name>."
        )
    safe = safe_name(name)
    candidate = inbox_dir / safe
    await asyncio.to_thread(_check_inbox_file, inbox_dir, candidate, safe)
    return candidate


async def fetch(
    *,
    message_id: str,
    attachment: Attachment | None,
    typed_name: str | None,
    mode: str,
    inbox_dir: Path,
    download: Callable[[Attachment], Awaitable[bytes]] | None,
) -> Path:
    if mode not in ("download", "inbox"):
        raise ValueError(f"unknown attachments mode {mode!r}")
    if mode == "download" and attachment is not None and download is not None:
        if isinstance(attachment.size, int) and attachment.size > MAX_BYTES:
            raise _too_big()
        try:
            data = await download(attachment)
        except Exception:
            log.warning("attachment download failed; using the inbox instead", exc_info=True)
        else:
            if len(data) > MAX_BYTES:
                raise _too_big()
            target = inbox_dir / f"{safe_name(message_id)}_{safe_name(attachment.filename)}"
            await asyncio.to_thread(_write_new, inbox_dir, target, data)
            return target
    return await _from_inbox(attachment, typed_name, inbox_dir)
