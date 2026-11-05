from __future__ import annotations

import hashlib

from carbon_room.sources.period import parse_period
from carbon_room.sources.readers import read
from carbon_room.sources.store import store_file
from carbon_room.sources.validate import validate


def test_store_is_content_addressed(tmp_path):
    source = tmp_path / "invoice.csv"
    source.write_text("value", encoding="utf-8")
    first = store_file(source, tmp_path / "store")
    second = store_file(source, tmp_path / "store")
    assert first == second
    assert first[1] == hashlib.sha256(b"value").hexdigest()


def test_period_formats_and_verbatim_evidence_validation():
    assert parse_period("Billing period: 1 Sep 2026 – 30 Sep 2026") == ("2026-09-01", "2026-09-30")
    assert parse_period("Period: 2026-09-01 to 2026-09-30") == ("2026-09-01", "2026-09-30")
    assert parse_period('{"period_end":"2026-09-30","period_start":"2026-09-01"}') == ("2026-09-01", "2026-09-30")
    assert validate({"page": 0, "excerpt": "Usage: 48,200 kWh", "value": "48200"}, ["Usage: 48,200 kWh"])[0]
    assert not validate({"page": 0, "excerpt": "Usage was 48,200", "value": "48200"}, ["Usage: 48,200 kWh"])[0]


def test_reader_errors_are_safe_for_room_visible_failures(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    kind, failure = read(broken)
    assert kind == "cloud_invoice"
    assert failure == "unreadable broken.json"
