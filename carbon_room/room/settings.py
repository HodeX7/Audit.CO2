"""Environment variables to one typed Settings object."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from carbon_room.room.ports import AGENT_NAMES

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


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
    return "SWITCH_AGENT_" + agent.upper().replace("-", "_").replace(".", "_") + "_" + field


def read_env(env_file: str | Path = ".env") -> dict[str, str]:
    file_values = {k: (v if v is not None else "") for k, v in dotenv_values(env_file).items()}
    return {**file_values, **os.environ}


def _resolve(env: Mapping[str, str] | None) -> dict[str, str]:
    source = read_env(".env") if env is None else env
    return {k: v.strip() for k, v in source.items() if isinstance(v, str)}


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name, "")
    if value == "":
        return default
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValueError(f"{name} must be 1 or 0, got {value!r}")


def missing(env: Mapping[str, str] | None = None, *, for_run: bool = True) -> list[str]:
    values = _resolve(env)
    if not for_run:
        names = ["SWITCH_SERVER", "SWITCH_REGISTRATION_KEY"]
    else:
        names = ["SWITCH_SERVER", "SWITCH_ROOM_ID"]
        try:
            single = _flag(values, "CARBON_ROOM_SINGLE_AGENT", False)
        except ValueError:
            single = False
        agents = AGENT_NAMES[:1] if single else AGENT_NAMES
        for agent in agents:
            names += [env_name(agent, "ID"), env_name(agent, "KEY")]
    return [n for n in names if not values.get(n)]


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    values = _resolve(env)
    names = missing(values)
    if names:
        raise ValueError(f"missing settings: {', '.join(names)}")
    threads = _flag(values, "CARBON_ROOM_THREADS", True)
    single = _flag(values, "CARBON_ROOM_SINGLE_AGENT", False)
    mode = (values.get("CARBON_ROOM_ATTACHMENTS") or "inbox").lower()
    if mode not in ("download", "inbox"):
        raise ValueError(f"CARBON_ROOM_ATTACHMENTS must be download or inbox, got {mode!r}")
    agents = {
        a: AgentCreds(a, values[env_name(a, "ID")], values[env_name(a, "KEY")])
        for a in AGENT_NAMES
        if values.get(env_name(a, "ID")) and values.get(env_name(a, "KEY"))
    }
    return Settings(
        server=values["SWITCH_SERVER"].rstrip("/"),
        room_id=values["SWITCH_ROOM_ID"],
        agents=agents,
        threads=threads,
        attachments_mode=mode,
        single_agent=single,
        permalink_base=(values.get("MATTERMOST_PERMALINK_BASE", "").rstrip("/") or None),
        media_path=values.get("SWITCH_MEDIA_PATH") or None,
        inbox_dir=Path("data/inbox"),
    )
