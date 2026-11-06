"""Environment variables to one typed Settings object."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AgentCreds:
    name: str
    agent_id: str
    api_key: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    server: str
    room_id: str
    agents: dict[str, AgentCreds]
    threads: bool
    attachments_mode: str
    single_agent: bool
    permalink_base: str | None
    media_path: str | None
    inbox_dir: Path = Path("data/inbox")


def env_name(agent: str, field: Literal["ID", "KEY"]) -> str:
    raise NotImplementedError


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    raise NotImplementedError


def missing(env: Mapping[str, str] | None = None, *, for_run: bool = True) -> list[str]:
    raise NotImplementedError


def read_env(env_file: str | Path = ".env") -> dict[str, str]:
    raise NotImplementedError
