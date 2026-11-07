"""F2 data-centre and factor-selection contract tests."""

from decimal import Decimal

import pytest

from carbon_room.calc import calculator, run, units
from carbon_room.ledger import ledger


def test_lb_per_mwh_conversion_is_available_through_convert():
    assert units.convert(Decimal("429.983"), "lb/MWh", "kgCO2e/kWh") == Decimal("0.19503700802971")


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_pure_compute_rejects_nonpositive_or_nonfinite_activity(value):
    from tests.p2.test_p2_calculator import EGRID, claim, factor

    with pytest.raises(ValueError, match="positive finite"):
        calculator.compute(claim(value=value), factor(EGRID))


def test_data_centre_has_both_bases_and_repeat_run_is_idempotent(factor_db, close_id, add_claim):
    claim_id = add_claim(
        close_id,
        "dc-eu-west",
        "dc_it_kwh",
        "12000",
        pue="1.2",
        market_based_kgco2e="0",
        vendor_factor_ref="Ember 2024 IE",
    )
    first = run.calculate(factor_db, close_id)
    assert len(first) == 2
    location = ledger.latest_calculation(factor_db, claim_id, "location")
    market = ledger.latest_calculation(factor_db, claim_id, "market")
    assert location.kgco2e == Decimal("3899.0448")
    assert location.factor_id == "EMBER-2024-IE-dc_it_kwh"
    assert "1.2" in location.formula
    assert market.kgco2e == 0
    assert market.formula == "as reported by vendor (certificates)"
    before = factor_db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert run.calculate(factor_db, close_id) == first
    assert factor_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


def test_missing_pue_is_rejected_without_a_fabricated_data_centre_calculation(factor_db, close_id, add_claim):
    claim_id = add_claim(close_id, "dc-eu-west", "dc_it_kwh", "12000", market_based_kgco2e="0")
    with pytest.raises(ValueError, match="PUE"):
        run.calculate(factor_db, close_id)
    assert ledger.live_calculations(factor_db, claim_id) == []


def test_recompute_detects_tampered_data_centre_result(factor_db, close_id, add_claim):
    claim_id = add_claim(close_id, "dc-eu-west", "dc_it_kwh", "12000", pue="1.2", market_based_kgco2e="0")
    run.calculate(factor_db, close_id)
    claim = ledger.get_claim(factor_db, claim_id)
    location = ledger.latest_calculation(factor_db, claim_id, "location")
    factor = ledger.get_factor(factor_db, location.factor_id)
    assert calculator.recompute(location, claim, factor)[2]
    location.kgco2e += Decimal("0.01")
    assert not calculator.recompute(location, claim, factor)[2]
