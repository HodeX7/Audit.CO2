"""A claim may have one live calculation per basis, so a location-based and a market-based record can coexist."""

from __future__ import annotations

from decimal import Decimal

import pytest

from carbon_room.ledger import ledger
from carbon_room.models import Actor, Calculation, Claim, Source

SYSTEM = Actor("system", "calculator", "Calculator")
D = Decimal


@pytest.fixture
def claim_id(db):
    ledger.load_factors(db, [{"factor_id": "F-1", "source": "S", "version": "1", "year": "2026", "activity": "dc_it_kwh",
                              "geography": "IE", "value": "0.5", "unit": "kgCO2e/kWh", "citation": "test"}])
    close = ledger.create_close(db, "2026-10", ["dc-eu-west"], "FS-test", SYSTEM, "msg")
    ledger.add_source(db, Source("SRC-1", close, "dc-eu-west", "cloud_invoice", "f.json", "p", "sha", 1, "t", None, None,
                                 "OK", None), SYSTEM)
    claim = Claim("", close, "dc-eu-west", "2026-10", "dc_it_kwh", D("12000"), "kWh", "DC", "SRC-1", "x", "sha", 0,
                  None, None, "UNVERIFIED", "collector", None, None, {})
    return ledger.add_claim(db, claim, SYSTEM)


def calc(claim_id, kg, basis, formula="f"):
    return Calculation("", claim_id, "F-1", "1", D("12000"), "kWh", D("0.5"), "kgCO2e/kWh", D(kg), formula, basis)


def live_count(db, claim_id):
    return db.execute("SELECT COUNT(*) FROM calculations WHERE claim_id=? AND superseded_by IS NULL",
                      (claim_id,)).fetchone()[0]


def test_a_location_and_a_market_record_can_both_be_live(db, claim_id):
    ledger.add_calculation(db, calc(claim_id, "7200", "location"))
    ledger.add_calculation(db, calc(claim_id, "0", "market", "as reported by vendor"))
    assert live_count(db, claim_id) == 2
    assert ledger.latest_calculation(db, claim_id, "location").kgco2e == D("7200")
    assert ledger.latest_calculation(db, claim_id, "market").kgco2e == D("0")


def test_a_new_calculation_supersedes_only_the_same_basis(db, claim_id):
    first = ledger.add_calculation(db, calc(claim_id, "7200", "location"))
    ledger.add_calculation(db, calc(claim_id, "0", "market"))
    third = ledger.add_calculation(db, calc(claim_id, "7300", "location"))
    assert live_count(db, claim_id) == 2
    assert ledger.latest_calculation(db, claim_id, "location").calc_id == third
    assert ledger.latest_calculation(db, claim_id, "market").kgco2e == D("0")
    superseded = db.execute("SELECT superseded_by FROM calculations WHERE calc_id=?", (first,)).fetchone()[0]
    assert superseded == third


def test_a_basisless_calculation_still_supersedes_its_predecessor(db, claim_id):
    first = ledger.add_calculation(db, calc(claim_id, "10", None))
    second = ledger.add_calculation(db, calc(claim_id, "11", None))
    assert live_count(db, claim_id) == 1
    assert ledger.latest_calculation(db, claim_id).calc_id == second
    assert db.execute("SELECT superseded_by FROM calculations WHERE calc_id=?", (first,)).fetchone()[0] == second


def test_without_a_basis_the_location_record_is_preferred_over_market(db, claim_id):
    """Existing callers pass no basis; they must never silently get the market figure when a location one exists."""
    ledger.add_calculation(db, calc(claim_id, "7200", "location"))
    ledger.add_calculation(db, calc(claim_id, "0", "market"))
    assert ledger.latest_calculation(db, claim_id).kgco2e == D("7200")


def test_without_a_basis_a_lone_market_record_is_returned(db, claim_id):
    ledger.add_calculation(db, calc(claim_id, "0", "market"))
    assert ledger.latest_calculation(db, claim_id).basis == "market"


def test_asking_for_a_basis_that_has_no_record_returns_none(db, claim_id):
    ledger.add_calculation(db, calc(claim_id, "7200", "location"))
    assert ledger.latest_calculation(db, claim_id, "market") is None


def test_live_calculations_lists_every_basis(db, claim_id):
    ledger.add_calculation(db, calc(claim_id, "7200", "location"))
    ledger.add_calculation(db, calc(claim_id, "0", "market"))
    assert sorted(item.basis for item in ledger.live_calculations(db, claim_id)) == ["location", "market"]
    assert ledger.live_calculations(db, "CL-none") == []


def test_an_unknown_basis_is_rejected(db, claim_id):
    with pytest.raises(ValueError, match="basis"):
        ledger.add_calculation(db, calc(claim_id, "1", "spot"))


def test_the_graph_links_every_live_and_superseded_calculation_to_its_claim(db, claim_id):
    ledger.add_calculation(db, calc(claim_id, "7200", "location"))
    ledger.add_calculation(db, calc(claim_id, "0", "market"))
    rows = db.execute("SELECT COUNT(*) FROM edges WHERE rel='OF' AND dst=?", (claim_id,)).fetchone()[0]
    assert rows == 2
