"""make doctor: check every precondition and say how to fix each failure."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str


CHECK_NAMES: tuple[str, ...] = (
    "Docker is running", "Switch server answers /health", "Four agent keys are in .env", "Room id is set",
    "people.yaml has no placeholders", "carbon_room.yaml is present", "Database initialises",
    "Replay cache covers every seed file", "API key present (live mode only)")


def run_checks(*, env: Mapping[str, str], runner: Callable[..., Any] = subprocess.run,
               transport: httpx.BaseTransport | None = None, repo_root: Path = Path(".")) -> list[Check]:
    raise NotImplementedError


def format_checks(checks: list[Check]) -> str:
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError
