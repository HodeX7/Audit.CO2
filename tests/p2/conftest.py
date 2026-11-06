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


@pytest.fixture
def close_id(factor_db):
    """An October close over the three configured sites, locked to the default factor set."""
    created = ledger.create_close(factor_db, "2026-10", BOUNDARY, config.load_config()["default_factor_set"],
                                  actors.CALCULATOR, "msg-start")
    factor_db.commit()
    return created
