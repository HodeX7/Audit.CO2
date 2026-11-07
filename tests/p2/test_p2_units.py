from decimal import Decimal

import pytest

from carbon_room.calc import units


def test_energy_and_mass_conversions_are_exact():
    assert units.convert(Decimal("48.3"), "MWh", "kWh") == Decimal("48300.0")
    assert units.convert(Decimal("2500"), "kgCO2e", "tCO2e") == Decimal("2.500")
    assert units.convert(Decimal("7"), "L", "L") == Decimal("7")


def test_unknown_pair_raises_instead_of_guessing():
    with pytest.raises(units.UnsupportedUnit):
        units.convert(Decimal(1), "L", "kWh")


def test_factor_denominator():
    assert units.denominator("kgCO2e/kWh") == "kWh"
    assert units.denominator("kgCO2e/L") == "L"
    with pytest.raises(units.UnsupportedUnit):
        units.denominator("kgCO2e/gallon")


def test_published_unit_conversions_match_the_catalogue_values():
    assert units.lb_per_mwh_to_kg_per_kwh(Decimal("429.983")) == Decimal("0.19503700802971")
    assert units.g_per_kwh_to_kg_per_kwh(Decimal("270.719")) == Decimal("0.270719")
