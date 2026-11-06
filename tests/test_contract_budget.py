from __future__ import annotations

import pytest

from carbon_room.ledger import ledger
from carbon_room.ledger.budget import charge, usage
from carbon_room.models import Actor, BudgetExceeded


def test_charge_warns_then_stops_before_cap(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg")
    assert charge(db, close_id, "collector", 85, limit=100) == "warn"
    with pytest.raises(BudgetExceeded):
        charge(db, close_id, "collector", 20, limit=100)
    assert usage(db, close_id)["collector"]["state"] == "warn"


def test_charge_rejects_negative_or_non_integer_tokens(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg")
    for invalid in (-1, True, 1.5):
        with pytest.raises(ValueError, match="non-negative integer"):
            charge(db, close_id, "collector", invalid)
