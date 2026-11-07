"""A fresh developer ledger must include the immutable factor catalogue."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from carbon_room.ledger import connect

ROOT = Path(__file__).resolve().parents[1]


def test_cli_init_loads_factors_and_is_repeatable(tmp_path):
    env = dict(os.environ, CARBON_ROOM_CONFIG_DIR=str(ROOT / "config"), PYTHONPATH=str(ROOT))
    for _ in range(2):
        result = subprocess.run([sys.executable, "-m", "carbon_room", "init"],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
    with connect(tmp_path / "var/carbon_room.db") as db:
        rows = db.execute("SELECT COUNT(*) FROM factors").fetchone()[0]
        assert rows == len((ROOT / "config/factors.csv").read_text(encoding="utf-8").splitlines()) - 1
