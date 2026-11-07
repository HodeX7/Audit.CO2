"""make doctor: check every precondition and say how to fix each failure."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from carbon_room.room import identity, settings


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


def _docker(runner: Callable[..., Any]) -> Check:
    name, fix = CHECK_NAMES[0], "Start Docker Desktop (the bundled Mattermost needs it)."
    try:
        result = runner(["docker", "info"], capture_output=True, timeout=20)
    except FileNotFoundError:
        return Check(name, False, "docker is not installed", fix)
    except subprocess.TimeoutExpired:
        return Check(name, False, "docker info timed out", fix)
    if result.returncode != 0:
        return Check(name, False, "docker info failed", fix)
    return Check(name, True, "", "")


def _switch(env: Mapping[str, str], transport: httpx.BaseTransport | None) -> Check:
    name = CHECK_NAMES[1]
    server = env.get("SWITCH_SERVER", "").strip().rstrip("/")
    if not server:
        return Check(name, False, "SWITCH_SERVER is not set",
                     "Put the server address from Switch Console in .env as SWITCH_SERVER.")
    try:
        with httpx.Client(transport=transport, timeout=5) as client:
            resp = client.get(f"{server}/health")
    except httpx.TransportError:
        return Check(name, False, f"can't reach {server}",
                     "Start the server in Switch Console (Run a server on this computer), "
                     "then copy its address.")
    if "text/html" in resp.headers.get("content-type", "") or resp.text.strip().startswith("<"):
        return Check(name, False, "that address served a web page",
                     "That's the Gateway. Use the server address Switch Console shows, not the Gateway.")
    if resp.status_code == 200:
        return Check(name, True, server, "")
    if resp.status_code == 401:
        return Check(name, False, "401 from /health",
                     "Right host, wrong path: use the server address, not the Gateway.")
    return Check(name, False, f"/health returned {resp.status_code}",
                 "Check the server address in Switch Console.")


def _agent_keys(env: Mapping[str, str]) -> Check:
    names = [n for n in settings.missing(env) if n.startswith("SWITCH_AGENT_")]
    if not names:
        return Check(CHECK_NAMES[2], True, "", "")
    return Check(CHECK_NAMES[2], False, "missing: " + ", ".join(names), "Run make register.")


def _room_id(env: Mapping[str, str]) -> Check:
    if env.get("SWITCH_ROOM_ID", "").strip():
        return Check(CHECK_NAMES[3], True, "", "")
    return Check(CHECK_NAMES[3], False, "SWITCH_ROOM_ID is not set",
                 "Create the emissions-reporting room and put its id in .env as SWITCH_ROOM_ID "
                 "(docs/setup-switch.md).")


def _people() -> Check:
    problems = identity.placeholders()
    if not problems:
        return Check(CHECK_NAMES[4], True, "", "")
    return Check(CHECK_NAMES[4], False, "; ".join(problems),
                 "Fill in switch_ids and username for lead and priya in config/people.yaml "
                 "(docs/setup-switch.md).")


def _yaml_present(config_dir: Path) -> Check:
    if (config_dir / "carbon_room.yaml").is_file():
        return Check(CHECK_NAMES[5], True, "", "")
    return Check(CHECK_NAMES[5], False, f"not found in {config_dir}",
                 "Pull main; P2 owns config/carbon_room.yaml.")


def _database(runner: Callable[..., Any], repo_root: Path) -> Check:
    name = CHECK_NAMES[6]
    fix = "Run .venv/bin/python -m carbon_room init and read the error."
    try:
        result = runner([sys.executable, "-m", "carbon_room", "init"], cwd=repo_root,
                        capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return Check(name, False, "init timed out", fix)
    if result.returncode == 0:
        return Check(name, True, "", "")
    lines = [ln for ln in (result.stderr or "").splitlines() if ln.strip()]
    return Check(name, False, lines[-1] if lines else f"exit {result.returncode}", fix)


def _mode(config_dir: Path) -> str | None:
    path = config_dir / "carbon_room.yaml"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    llm = data.get("llm") if isinstance(data, dict) else None
    mode = llm.get("mode") if isinstance(llm, dict) else None
    return str(mode) if mode else "unknown"


def _replay_cache(mode: str | None, repo_root: Path) -> Check:
    name = CHECK_NAMES[7]
    if mode is None:
        return Check(name, True, "skipped: no carbon_room.yaml", "")
    if mode != "replay":
        return Check(name, True, f"not needed (mode={mode})", "")
    cache = repo_root / "data" / "cache" / "extractions"
    missing: list[str] = []
    for folder in sorted((repo_root / "data" / "seed").glob("*/")):
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            if f.is_file() and f.suffix != ".json":
                digest = hashlib.sha256(f.read_bytes()).hexdigest()
                if not (cache / f"{digest}.json").is_file():
                    missing.append(f.name)
    if not missing:
        return Check(name, True, "", "")
    return Check(name, False,
                 f"{len(missing)} seed file(s) have no cached extraction: {', '.join(sorted(missing))}",
                 "Run make refresh-cache with an API key, or set llm.mode to rules in "
                 "config/carbon_room.yaml (ask P2).")


def _api_key(mode: str | None, env: Mapping[str, str]) -> Check:
    name = CHECK_NAMES[8]
    if mode == "live":
        if env.get("ANTHROPIC_API_KEY", "").strip():
            return Check(name, True, "", "")
        return Check(name, False, "ANTHROPIC_API_KEY is not set",
                     "Put ANTHROPIC_API_KEY in .env, or use llm.mode rules or replay.")
    return Check(name, True, f"not needed (mode={mode or 'unknown'})", "")


def run_checks(*, env: Mapping[str, str], runner: Callable[..., Any] = subprocess.run,
               transport: httpx.BaseTransport | None = None, repo_root: Path = Path(".")) -> list[Check]:
    config_dir = Path(env.get("CARBON_ROOM_CONFIG_DIR") or repo_root / "config")
    mode = _mode(config_dir)
    return [
        _docker(runner),
        _switch(env, transport),
        _agent_keys(env),
        _room_id(env),
        _people(),
        _yaml_present(config_dir),
        _database(runner, repo_root),
        _replay_cache(mode, repo_root),
        _api_key(mode, env),
    ]


def format_checks(checks: list[Check]) -> str:
    lines: list[str] = []
    for c in checks:
        if c.ok:
            lines.append(f"✓ {c.name}")
        else:
            lines.append(f"✗ {c.name} — {c.detail}")
            lines.append(f"    fix: {c.fix}")
    failed = sum(1 for c in checks if not c.ok)
    lines.append("All 9 checks passed." if failed == 0 else f"{failed} of 9 checks failed.")
    return "\n".join(lines)


def main() -> int:
    env = settings.read_env(".env")
    checks = run_checks(env=env)
    print(format_checks(checks))
    return 1 if any(not c.ok for c in checks) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
