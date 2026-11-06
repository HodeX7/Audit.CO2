"""Content-addressed source-file storage."""

from __future__ import annotations

import hashlib
from pathlib import Path


def store_file(path: str | Path, root: str | Path = "var/store") -> tuple[str, str]:
    """Copy source bytes once to `var/store/<sha256><suffix>` and return path/hash."""
    source = Path(path)
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    destination = Path(root) / f"{digest}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(content)
    return str(destination), digest
