"""Contract configuration loaders.

Production uses PyYAML, declared in :mod:`pyproject.toml`.  The small fallback
keeps the repository's P1 sites file readable in an offline development venv;
it accepts the same limited mapping/list shape as ``sites.yaml``.
"""

from __future__ import annotations

import ast
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _config_dir() -> Path:
    return Path(os.environ.get("CARBON_ROOM_CONFIG_DIR", DEFAULT_CONFIG_DIR))


def _flow_value(value: str) -> Any:
    """Decode the compact mapping/list notation used by the P1 site config."""
    quoted = value.strip()
    if quoted.startswith("{") or quoted.startswith("["):
        # YAML flow entries in this project use bare keys and scalar values.
        import re

        pythonish = re.sub(r"([,{]\s*)([A-Za-z_][\w-]*)\s*:", r"\1'\2':", quoted)
        pythonish = re.sub(r"(:\s*)([A-Za-z_][\w-]*)(?=\s*[,}\]])", r"\1'\2'", pythonish)
        return ast.literal_eval(pythonish)
    return quoted.strip('"\'')


def _minimal_sites_yaml(text: str) -> dict[str, Any]:
    """Read the deliberately small P1 sites-file subset when PyYAML is unavailable."""
    sites: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    diesel_factor: dict[str, Any] | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() == "sites:":
            continue
        stripped = raw.strip()
        if stripped.startswith("- id:"):
            current = {"id": stripped.partition(":")[2].strip()}
            sites.append(current)
            continue
        if stripped.startswith("diesel_factor:"):
            diesel_factor = _flow_value(stripped.partition(":")[2].strip())
            continue
        if current is None or ":" not in stripped:
            raise ValueError("PyYAML is required for this configuration shape")
        key, _, value = stripped.partition(":")
        current[key.strip()] = _flow_value(value.strip())
    if not sites:
        raise ValueError("sites.yaml must define at least one site")
    return {"sites": sites, "diesel_factor": diesel_factor or {}}


def _read_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if path.name == "sites.yaml":
            return _minimal_sites_yaml(text)
        raise RuntimeError("PyYAML is required to read this configuration file")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping")
    return loaded


@lru_cache
def load_config() -> dict[str, Any]:
    """Load P2's shared settings, if that team-owned file is present."""
    return _read_yaml(_config_dir() / "carbon_room.yaml")


@lru_cache
def load_sites() -> dict[str, Any]:
    """Load P1-owned site boundaries and expected source kinds."""
    return _read_yaml(_config_dir() / "sites.yaml")


@lru_cache
def load_people() -> dict[str, Any]:
    """Load P3-owned people mapping, if supplied."""
    return _read_yaml(_config_dir() / "people.yaml")


def site(site_id: str) -> dict[str, Any]:
    """Return one configured site or a helpful boundary error."""
    for configured in load_sites()["sites"]:
        if configured["id"] == site_id:
            return configured
    valid = ", ".join(item["id"] for item in load_sites()["sites"])
    raise ValueError(f"unknown site {site_id!r}; valid sites: {valid}")


def expected_sources(month: str) -> list[tuple[str, str, str]]:
    """Return expected `(site, source kind, activity)` pairs for a close month."""
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must use YYYY-MM")
    return [
        (configured["id"], expected["kind"], expected["activity"])
        for configured in load_sites()["sites"]
        for expected in configured.get("expected", [])
    ]


def site_owner(site_id: str) -> str:
    """Return the configured human owner for a site."""
    return str(site(site_id)["owner"])


def clear_caches() -> None:
    """Clear configuration caches after a test changes ``CARBON_ROOM_CONFIG_DIR``."""
    load_config.cache_clear()
    load_sites.cache_clear()
    load_people.cache_clear()
