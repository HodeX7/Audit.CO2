"""make reset-demo: wipe local state and re-initialise the database."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

PROMPT: str = "This deletes var/, out/ and data/inbox/ and archives the room. Type reset to continue: "
ROOM_STEPS: str = ("Room reset isn't automated yet. In Mattermost, archive october-close and create a new "
                   "october-close, invite the four agents, and put its id in .env as SWITCH_ROOM_ID.")


def reset_local(repo_root: Path) -> list[Path]:
    raise NotImplementedError


def main(argv: Sequence[str] | None = None, *, input_fn: Callable[[str], str] = input,
         runner: Callable[..., Any] = subprocess.run, repo_root: Path = Path(".")) -> int:
    raise NotImplementedError
