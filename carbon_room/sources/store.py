"""Content-addressed source-file storage."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from tempfile import mkstemp

from carbon_room.sources import readers


def store_file(path: str | Path, root: str | Path = "var/store") -> tuple[str, str]:
    """Copy source bytes once to `var/store/<sha256><suffix>` and return path/hash."""
    source = Path(path)
    if source.is_symlink():
        raise ValueError("symlink evidence is not allowed")
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as opened:
        metadata = os.fstat(opened.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("evidence must be a regular file")
        if metadata.st_size > readers.MAX_SOURCE_BYTES:
            raise ValueError("evidence exceeds the source size limit")
        content = opened.read(readers.MAX_SOURCE_BYTES + 1)
    if len(content) > readers.MAX_SOURCE_BYTES:
        raise ValueError("evidence exceeds the source size limit")
    digest = hashlib.sha256(content).hexdigest()
    destination = Path(root) / f"{digest}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("stored evidence must not be a symlink")
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError("stored evidence hash mismatch")
        return str(destination), digest
    fd, temporary_name = mkstemp(prefix=f".{digest}-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as staged:
            staged.write(content)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination), digest
