"""SPEC-16: the Makefile."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {"help", "setup", "seed", "register", "doctor", "run", "reset-demo", "test", "lint",
           "refresh-cache"}
needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")


def test_makefile_targets_exist_and_echo():
    lines = (ROOT / "Makefile").read_text().splitlines()
    found = {}
    for i, line in enumerate(lines):
        m = re.match(r"^([a-z-]+):", line)
        if m:
            found[m.group(1)] = lines[i + 1]
    assert set(found) == TARGETS
    for target, first in found.items():
        assert first.startswith('\t@echo "→ '), target


@needs_make
@pytest.mark.parametrize("target", sorted(TARGETS))
def test_make_dry_run_every_target(target):
    assert subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True).returncode == 0


@needs_make
def test_help_is_default_target():
    out = subprocess.run(["make", "-n"], cwd=ROOT, capture_output=True, text=True)
    assert "Carbon Room make targets" in out.stdout
