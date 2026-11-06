"""Dependency boundaries for P3 code (SPEC-01 section 6)."""

from __future__ import annotations

import re
from pathlib import Path

AGENT_MODULES = ("orchestrator", "gaps", "resolution", "publish", "reports", "ask", "notices", "hooks")
ROOT = Path(__file__).resolve().parents[2]


def test_p3_code_never_imports_ledger():
    files = list((ROOT / "carbon_room" / "room").glob("*.py"))
    for name in AGENT_MODULES:
        path = ROOT / "carbon_room" / "agents" / f"{name}.py"
        if path.exists():
            files.append(path)
    patterns = [
        r"carbon_room\.ledger",
        r"from carbon_room import ledger",
        r"^\s*(from|import)\s+(tests|fakes)\b",
    ]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern, text, re.MULTILINE), f"{path} matches {pattern!r}"


def test_fakes_live_only_under_tests():
    assert list((ROOT / "carbon_room").rglob("fake*.py")) == []
