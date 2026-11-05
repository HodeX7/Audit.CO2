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
