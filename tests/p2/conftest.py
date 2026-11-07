"""Fixtures shared by the P2 tests: repo config, a loaded factor catalogue, and a close."""

from __future__ import annotations

import pytest

from carbon_room import actors, config
from carbon_room.calc import factors
from carbon_room.ledger import ledger

BOUNDARY = ["hq", "warehouse-2", "dc-eu-west"]


@pytest.fixture(autouse=True)
def repo_config(monkeypatch):
    """Use the repository's config directory, whatever an earlier test pointed the loader at."""
    monkeypatch.delenv("CARBON_ROOM_CONFIG_DIR", raising=False)
    config.clear_caches()
    yield
    config.clear_caches()


@pytest.fixture
def factor_db(db):
    """A ledger with the factor catalogue loaded."""
    factors.load(db)
    db.commit()
    return db


UNITS = {"electricity_kwh": "kWh", "diesel_l": "L", "dc_it_kwh": "kWh"}


@pytest.fixture
def add_claim(factor_db):
    """Return a builder that inserts a source and one UNVERIFIED claim, without going through ingestion."""
    from decimal import Decimal

    from carbon_room.models import Claim, Source

    counter = {"n": 0}

    def build(close, site, activity, value, *, month="2026-10", period=None, file_name=None, **attributes):
        counter["n"] += 1
        number = counter["n"]
        year, mon = int(month[:4]), int(month[5:])
        start, end = period or (f"{month}-01", f"{month}-28")
        printed = f"Billing period: {start} to {end}"
        name = file_name or f"{site}_{activity}_{month}_{number}.pdf"
        source = Source(
            f"SRC-{number:04d}",
            close,
            site,
            "utility_pdf",
            name,
            "stored",
            f"sha-{number}",
            1,
            f"{printed}\nUsage: {value} {UNITS[activity]}",
            start,
            end,
            "OK",
            None,
        )
        ledger.add_source(factor_db, source, actors.CALCULATOR)
        claim = Claim(
            "",
            close,
            site,
            f"{year}-{mon:02d}",
            activity,
            Decimal(str(value)),
            UNITS[activity],
            {"diesel_l": "1", "dc_it_kwh": "DC"}.get(activity, "2"),
            source.source_doc_id,
            f"{value} {UNITS[activity]}",
            source.sha256,
            0,
            None,
            None,
            "UNVERIFIED",
            "collector",
            None,
            None,
            attributes,
        )
        return ledger.add_claim(factor_db, claim, actors.CALCULATOR)

    return build


@pytest.fixture
def close_id(factor_db):
    """An October close over the three configured sites, locked to the default factor set."""
    created = ledger.create_close(
        factor_db, "2026-10", BOUNDARY, config.load_config()["default_factor_set"], actors.CALCULATOR, "msg-start"
    )
    factor_db.commit()
    return created
