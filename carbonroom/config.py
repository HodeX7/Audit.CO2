"""Settings for Carbon Room, read from environment variables (and `.env` if present).

See `.env.example` for every variable. Nothing here holds a secret by default.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

_ENV_LOADED = False


def load_env() -> None:
    """Load `.env` from the current directory once (no error if python-dotenv is missing)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def env(name: str, default: str | None = None) -> str | None:
    load_env()
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def repo_root() -> Path:
    """The folder that holds `contracts/` (the repo root in a normal checkout)."""
    return Path(__file__).resolve().parents[1]


def db_path() -> Path:
    return Path(env("CR_DB_PATH", "./carbonroom.db")).expanduser()


def data_dir() -> Path:
    return Path(env("CR_DATA_DIR", "./data")).expanduser()


def seed_dir() -> Path:
    return data_dir() / "seed"


def inbox_dir() -> Path:
    return data_dir() / "inbox"


def store_dir() -> Path:
    """Content-addressed copies of uploaded documents (not committed)."""
    return data_dir() / "store"


def extraction_cache_dir() -> Path:
    return seed_dir() / "extractions"


def factor_set() -> str | None:
    return env("CR_FACTOR_SET")


def now_iso() -> str:
    """Current UTC time as ISO-8601. Set CR_NOW to pin it (tests, reproducible demos)."""
    pinned = env("CR_NOW")
    if pinned:
        return pinned
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def schema_path() -> Path:
    candidates = [
        repo_root() / "contracts" / "schema.sql",
        Path(__file__).resolve().parent / "_contracts" / "schema.sql",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("contracts/schema.sql not found; run from a full checkout of the repo")
