from __future__ import annotations

import hashlib

import pytest

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


def test_store_rejects_a_corrupt_existing_content_address(tmp_path):
    source = tmp_path / "invoice.csv"
    source.write_bytes(b"trusted evidence")
    digest = hashlib.sha256(b"trusted evidence").hexdigest()
    store = tmp_path / "store"
    store.mkdir()
    (store / f"{digest}.csv").write_bytes(b"different bytes")
    with pytest.raises(ValueError, match="stored evidence hash mismatch"):
        store_file(source, store)


def test_period_formats_and_verbatim_evidence_validation():
    assert parse_period("Billing period: 1 Sep 2026 – 30 Sep 2026") == ("2026-09-01", "2026-09-30")
    assert parse_period("Period: 2026-09-01 to 2026-09-30") == ("2026-09-01", "2026-09-30")
    assert parse_period('{"period_end":"2026-09-30","period_start":"2026-09-01"}') == ("2026-09-01", "2026-09-30")
    assert validate(
        {"activity": "electricity_kwh", "unit": "kWh", "page": 0, "excerpt": "Usage: 48,200 kWh", "value": "48200"},
        ["Usage: 48,200 kWh"],
    )[0]
    assert not validate(
        {"activity": "electricity_kwh", "unit": "kWh", "page": 0, "excerpt": "Usage was 48,200", "value": "48200"},
        ["Usage: 48,200 kWh"],
    )[0]
    assert not validate(
        {"activity": "electricity_kwh", "unit": "kWh", "page": 0, "excerpt": "0 kWh", "value": "0"}, ["0 kWh"]
    )[0]
    assert not validate(
        {"activity": "override_close", "unit": "kWh", "page": 0, "excerpt": "1 kWh", "value": "1"}, ["1 kWh"]
    )[0]
    assert not validate(
        {"activity": ["electricity_kwh"], "unit": "kWh", "page": 0, "excerpt": "1 kWh", "value": "1"}, ["1 kWh"]
    )[0]


@pytest.mark.parametrize(
    "text",
    [
        "Period: 2026-99-01 to 2026-99-30",
        "Billing period: 31 Oct 2026 – 1 Oct 2026",
        '{"period_start":"2026-10-31","period_end":"2026-10-01"}',
    ],
)
def test_period_parser_rejects_invalid_or_reversed_calendar_dates(text):
    with pytest.raises(ValueError, match="billing period"):
        parse_period(text)


def test_reader_errors_are_safe_for_room_visible_failures(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    kind, failure = read(broken)
    assert kind == "cloud_invoice"
    assert failure == "unreadable broken.json"
