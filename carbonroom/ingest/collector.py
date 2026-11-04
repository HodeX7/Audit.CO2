"""Collector: files in, `source_docs` rows out.

Inputs
  * any path(s) given to `carbonroom ingest`
  * the watch folder `data/inbox/` - the hand-off agreed with Akshar's agents:
        data/inbox/<room>/<file>                e.g. data/inbox/cr-site-reno/reno-oct.pdf
        data/inbox/<room>/<file>.meta.json      optional sidecar:
            {"received_from": "lena", "room": "cr-site-reno", "thread_id": "...", "message_id": "...",
             "gap_id": "GAP-012"}
    The room defaults to the folder name; received_from defaults to "inbox".

Rules
  * identity = sha256 of the bytes; a known hash is skipped as a duplicate (idempotent)
  * kind comes from keyword rules first; the proposer's kind is used only when rules say "other"
  * files under data/seed are referenced in place (committed, immutable); anything else is
    copied to data/store/<sha256><ext> so the evidence can't change or disappear later
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from carbonroom import config
from carbonroom.ingest.hashing import sha256_file

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
META_SUFFIX = ".meta.json"
PROCESSED_DIR = "_processed"


@dataclass
class Incoming:
    path: Path
    sha256: str
    received_from: str | None
    room: str | None
    meta: dict[str, Any] = field(default_factory=dict)


def _is_meta(path: Path) -> bool:
    return path.name.endswith(META_SUFFIX)


def iter_files(target: Path) -> Iterator[Path]:
    """Supported files under `target` (a file or folder), sorted, skipping sidecars and _processed/."""
    if target.is_file():
        if not _is_meta(target):
            yield target
        return
    for path in sorted(target.rglob("*")):
        if not path.is_file() or _is_meta(path) or path.name.startswith("."):
            continue
        if PROCESSED_DIR in path.parts:
            continue
        if path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def read_sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.with_name(path.name + META_SUFFIX)
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {"sidecar_error": "invalid JSON"}
    return {}


def room_from_path(path: Path) -> str | None:
    parent = path.parent.name
    return parent if parent.startswith("cr-") else None


def describe(path: Path, *, received_from: str | None = None, room: str | None = None,
             meta: dict[str, Any] | None = None) -> Incoming:
    """Hash a file and work out who sent it from where (CLI flags win over the sidecar)."""
    sidecar = read_sidecar(path)
    merged = {**sidecar, **(meta or {})}
    return Incoming(
        path=path,
        sha256=sha256_file(path),
        received_from=received_from or sidecar.get("received_from") or "inbox",
        room=room or sidecar.get("room") or room_from_path(path),
        meta={k: v for k, v in merged.items() if k not in ("received_from", "room") and v is not None},
    )


def _relative(path: Path) -> str:
    resolved = path.resolve()
    for base in (Path.cwd().resolve(), config.repo_root().resolve()):
        try:
            return resolved.relative_to(base).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


def store(incoming: Incoming) -> str:
    """Return the path to record in source_docs (seed files in place, others content-addressed)."""
    try:
        incoming.path.resolve().relative_to(config.seed_dir().resolve())
        return _relative(incoming.path)
    except ValueError:
        pass
    dest_dir = config.store_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{incoming.sha256}{incoming.path.suffix.lower()}"
    if not dest.exists():
        shutil.copy2(incoming.path, dest)
    return _relative(dest)


def move_processed(path: Path, inbox: Path) -> Path | None:
    """Move an inbox file (and its sidecar) to data/inbox/_processed/<same relative path>."""
    try:
        rel = path.resolve().relative_to(inbox.resolve())
    except ValueError:
        return None
    dest = inbox / PROCESSED_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), dest)
    sidecar = path.with_name(path.name + META_SUFFIX)
    if sidecar.exists():
        shutil.move(str(sidecar), dest.with_name(dest.name + META_SUFFIX))
    return dest
