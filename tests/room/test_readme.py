"""Documentation commands and links stay executable as code evolves."""

import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote

from carbon_room.room import grammar

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_structure_and_commands():
    assert re.findall(r"^## (.+)$", README, re.M) == [
        "What it is", "How Switch is used", "Quick start", "Running the demo close",
        "Traps and the rules that catch them", "What is synthetic and what is not claimed",
        "Spike results and fallbacks", "Architecture", "Team and track",
    ]
    targets = set(re.findall(r"^([a-z-]+):", (ROOT / "Makefile").read_text(), re.M))
    assert set(re.findall(r"make ([a-z-]+)", README)) <= targets
    assert (ROOT / "tests/test_publish_needs_room.py").is_file()
    for fake_total in ("22.9", "29.2", "13.2", "29184", "22900"):
        assert fake_total not in README


def test_demo_commands_parse_to_documented_intents():
    demo = README.split("## Running the demo close", 1)[1].split("## Traps", 1)[0]
    commands = re.findall(r"`(@[^`]+|G-\d+ [^`]+)`\s*<!-- ([a-z.]+) -->", demo)
    assert len(commands) >= 8
    for command, kind in commands:
        assert grammar.parse(command, in_thread=False, today=date(2026, 11, 5)).kind == kind


def test_local_links_exist():
    for destination in re.findall(r"\]\(([^)]+)\)", README):
        if destination.startswith(("https:", "http:")):
            continue
        assert (ROOT / unquote(destination)).exists(), destination
