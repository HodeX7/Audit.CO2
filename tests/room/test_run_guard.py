"""The executable refuses to start inside a test-double process."""

import subprocess
import sys
from pathlib import Path
from types import ModuleType

from carbon_room.room import run


def test_main_refuses_test_doubles_before_loading_credentials(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "fakes.fake_core", ModuleType("fakes.fake_core"))
    monkeypatch.setattr(run, "load_settings", lambda: (_ for _ in ()).throw(AssertionError("settings read")))
    assert run.main() == 3
    assert "refusing to run with test doubles loaded" in capsys.readouterr().err


def test_main_reports_missing_settings_without_secrets(tmp_path):
    import os

    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("SWITCH_", "CARBON_ROOM_"))}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    proc = subprocess.run([sys.executable, "-m", "carbon_room.room.run"],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 1
    assert "missing settings" in proc.stderr
