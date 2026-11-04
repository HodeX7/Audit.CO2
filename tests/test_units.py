from decimal import Decimal

import pytest

from carbonroom.ingest.units import UnitError, canonical_unit, normalize, unit_in_text


@pytest.mark.parametrize(
    "category, qty, unit, want_qty, want_unit",
    [
        ("electricity", "191300", "kWh", "191300", "kWh"),
        ("electricity", "14.62", "MWh", "14620", "kWh"),
        ("electricity", "15.08", "megawatt hours", "15080", "kWh"),
        ("cloud_compute", "38200", "KWH", "38200", "kWh"),
        ("natural_gas", "7700", "therms", "7700", "therm"),
        ("natural_gas", "770", "Dth", "7700", "therm"),
        ("natural_gas", "770", "MMBtu", "7700", "therm"),
        ("diesel", "500.0", "gal", "500.0", "gal"),
        ("diesel", "1892.7", "L", "499.998", "gal"),
        ("diesel", "3.785411784", "litres", "1.000", "gal"),
        ("rec_mwh", "120", "MWh", "120", "MWh"),
    ],
)
def test_normalize(category, qty, unit, want_qty, want_unit):
    n = normalize(category, Decimal(qty), unit)
    assert n.quantity == Decimal(want_qty) and n.unit == want_unit
    assert n.original_quantity == qty  # the original is always kept


@pytest.mark.parametrize("category, unit", [("natural_gas", "ccf"), ("electricity", "kW"), ("diesel", "kg"),
                                            ("steam", "kWh")])
def test_units_that_need_an_assumption_are_refused(category, unit):
    with pytest.raises(UnitError):
        normalize(category, Decimal("1"), unit)


def test_unit_tokens():
    assert canonical_unit("Kilowatt-Hours") == "kWh"
    assert unit_in_text("kWh", "Total: 191,300 kWh")
    assert not unit_in_text("kWh", "Water usage effectiveness (WUE): 0.42 L/kWh")  # L/kWh is not kWh
    assert unit_in_text("L/kWh", "Water usage effectiveness (WUE): 0.42 L/kWh")
    assert unit_in_text("L", "Quantity delivered: 1,892.7 L")
    assert not unit_in_text("L", "Quantity delivered: 500.0 gal")
