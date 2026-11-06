"""Replay-cache access for deterministic, no-network demo ingestion."""

from __future__ import annotations

import json
from pathlib import Path


def cache_path(sha256: str, root: str | Path = "data/cache/extractions") -> Path:
    return Path(root) / f"{sha256}.json"


def load(sha256: str, root: str | Path = "data/cache/extractions") -> list[dict]:
    """Load an extraction replay or explain how to fill the missing cache."""
    path = cache_path(sha256, root)
    if not path.exists():
        raise FileNotFoundError(f"replay cache miss for {sha256}; run `make refresh-cache` with live model access")
    return json.loads(path.read_text(encoding="utf-8"))


def save(sha256: str, candidates: list[dict], root: str | Path = "data/cache/extractions") -> None:
    path = cache_path(sha256, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
