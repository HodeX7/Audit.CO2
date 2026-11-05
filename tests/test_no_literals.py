"""Prevent contract identifiers and configured sites leaking into reusable code."""

from __future__ import annotations

import re
from pathlib import Path

from carbon_room import config


def test_contract_code_has_no_seed_specific_sites_months_or_ids():
    site_ids = {item["id"] for item in config.load_sites()["sites"]}
    forbidden = [*site_ids, r"\b\d{4}-\d{2}\b", r"\b(?:CL|G|S)-\d+\b"]
    root = Path("carbon_room")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            assert not re.search(value, text), f"{path} contains contract-specific literal {value!r}"
