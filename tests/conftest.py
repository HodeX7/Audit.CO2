"""Contract-package test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def db(tmp_path):
    """Isolated SQLite ledger initialised with the contract schema."""
    from carbon_room.ledger import connect, init_db

    conn = connect(tmp_path / "carbon_room.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def factor_db(db):
    """P2 integration tests start from the checked-in factor catalogue."""
    from carbon_room.calc import factors

    factors.load(db)
    db.commit()
    return db


@pytest.fixture
def close_id(factor_db):
    """An isolated October close using the shared contract boundary."""
    from carbon_room import config
    from carbon_room.actors import CALCULATOR
    from carbon_room.ledger import ledger

    config.clear_caches()
    close = ledger.create_close(
        factor_db,
        "2026-10",
        ["hq", "warehouse-2", "dc-eu-west"],
        config.load_config()["default_factor_set"],
        CALCULATOR,
        "msg-start",
    )
    factor_db.commit()
    return close
