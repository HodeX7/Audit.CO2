"""SPEC-16: make reset-demo (local part)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from carbon_room.room.reset import PROMPT, ROOM_STEPS, main, reset_local

ROOT = Path(__file__).resolve().parents[2]


class Runner:
    def __init__(self, returncode=0, stderr=""):
        self.res = SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        return self.res


FILES = ["var/carbon_room.db", "var/store/x.pdf", "out/2026-10/v1/coverage.html", "data/inbox/.gitkeep",
         "data/inbox/bill.pdf", "data/inbox/sub/y.pdf", "data/seed/2026-10/a.pdf", "data/demo_uploads/d.pdf",
         "config/sites.yaml", ".env"]
KEPT = ["data/seed/2026-10/a.pdf", "data/demo_uploads/d.pdf", "config/sites.yaml", ".env"]


@pytest.fixture
def repo(tmp_path):
    for f in FILES:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return tmp_path


def test_reset_cancelled_deletes_nothing(repo, capsys):
    prompts, runner = [], Runner()

    def ask(p):
        prompts.append(p)
        return "no"

    assert main([], input_fn=ask, runner=runner, repo_root=repo) == 1
    assert "Cancelled." in capsys.readouterr().out
    assert all((repo / f).exists() for f in FILES)
    assert runner.calls == []
    assert prompts == [PROMPT]


def test_reset_local_keeps_gitkeep_and_seed(repo, capsys):
    runner = Runner()
    assert main(["--yes", "--local-only"], runner=runner, repo_root=repo) == 0
    assert not (repo / "var").exists() and not (repo / "out").exists()
    assert [p.name for p in (repo / "data/inbox").iterdir()] == [".gitkeep"]
    assert all((repo / f).exists() for f in KEPT)
    assert runner.calls[0][0] == [sys.executable, "-m", "carbon_room", "init"]
    out = capsys.readouterr().out
    assert out.rstrip().endswith("Reset done.")
    assert ROOM_STEPS not in out


def test_reset_never_leaves_repo_root(repo):
    outside_dir = repo.parent / f"{repo.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "keep.txt"
    outside.write_text("keep")
    shutil.rmtree(repo / "var")
    (repo / "var").symlink_to(outside_dir, target_is_directory=True)
    (repo / "data/inbox/link.pdf").symlink_to(outside)
    reset_local(repo)
    assert outside.read_text() == "keep"
    assert outside_dir.is_dir()
    assert not os.path.lexists(repo / "var")
    assert not os.path.lexists(repo / "data/inbox/link.pdf")


def test_reset_typed_confirmation(repo):
    assert main([], input_fn=lambda p: "  reset ", runner=Runner(), repo_root=repo) == 0


def test_reset_prints_room_steps_without_local_only(repo, capsys):
    main(["--yes"], runner=Runner(), repo_root=repo)
    assert ROOM_STEPS in capsys.readouterr().out


def test_reset_init_failure(repo, capsys):
    assert main(["--yes"], runner=Runner(2, "bad\n"), repo_root=repo) == 1
    assert "Database init failed: bad" in capsys.readouterr().out


def test_reset_creates_missing_inbox(repo):
    shutil.rmtree(repo / "data/inbox")
    reset_local(repo)
    assert (repo / "data/inbox/.gitkeep").exists()


def test_reset_script_is_executable_and_exact():
    path = ROOT / "scripts" / "reset_demo.sh"
    text = path.read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert os.access(path, os.X_OK)
    assert '-m carbon_room.room.reset "$@"' in text
