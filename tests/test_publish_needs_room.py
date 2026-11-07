"""There is no local bypass for human mutation or publication."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from carbon_room import core
from carbon_room.models import Actor, NeedsRoomEvent

ROOT = Path(__file__).resolve().parents[1]
LEAD = Actor("human", "lead", "Lead", "lead")


def test_cli_has_no_human_mutation_command():
    result = subprocess.run([sys.executable, "-m", "carbon_room", "--help"], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert not re.search(r"\b(?:publish|resolve|approve)\b", result.stdout.lower())


def test_ingest_file_requires_room_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(NeedsRoomEvent):
        core.ingest_file("2026-10-v1", "x.pdf", LEAD, "")


def test_publish_requires_room_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(NeedsRoomEvent):
        core.publish("2026-10-v1", LEAD, "")


def test_only_room_facade_invokes_human_mutations():
    pattern = re.compile(r"\bcore\.(?:resolve|publish)\(")
    for path in (ROOT / "carbon_room").rglob("*.py"):
        if path.name == "core.py" or path.parts[-2] in ("room", "agents"):
            continue
        assert not pattern.search(path.read_text(encoding="utf-8")), path
