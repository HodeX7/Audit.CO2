"""make reset-demo: wipe local state and re-initialise the database."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

PROMPT: str = "This deletes var/, out/ and data/inbox/ and archives the room. Type reset to continue: "
ROOM_STEPS: str = ("Room reset isn't automated yet. In Mattermost, archive october-close and create a new "
                   "october-close, invite the four agents, and put its id in .env as SWITCH_ROOM_ID.")


def _remove(path: Path, parent: Path, root: Path) -> None:
    """Remove one path (never following symlinks), after checking it sits where it should."""
    if path.parent.resolve() != parent.resolve() or not path.parent.resolve().is_relative_to(root):
        raise RuntimeError(f"refusing to remove {path}: outside {root}")
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def reset_local(repo_root: Path) -> list[Path]:
    root = repo_root.resolve()
    removed: list[Path] = []
    for name in ("var", "out"):
        path = repo_root / name
        if path.is_symlink() or path.exists():
            _remove(path, repo_root, root)
            removed.append(path)
    inbox = repo_root / "data" / "inbox"
    if inbox.is_dir() and not inbox.is_symlink():
        for child in sorted(inbox.iterdir()):
            if child.name == ".gitkeep":
                continue
            _remove(child, inbox, root)
            removed.append(child)
    else:
        if inbox.is_symlink():
            inbox.unlink()
        inbox.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").touch()
    return removed


def _last_line(text: str | None) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def main(argv: Sequence[str] | None = None, *, input_fn: Callable[[str], str] = input,
         runner: Callable[..., Any] = subprocess.run, repo_root: Path = Path(".")) -> int:
    parser = argparse.ArgumentParser(prog="reset-demo")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.yes and input_fn(PROMPT).strip() != "reset":
        print("Cancelled.")
        return 1
    reset_local(repo_root)
    result = runner([sys.executable, "-m", "carbon_room", "init"], cwd=repo_root,
                    capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Database init failed: {_last_line(result.stderr)}")
        return 1
    if not args.local_only:
        print(ROOM_STEPS)
    print("Reset done.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
