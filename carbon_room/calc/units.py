"""Unit conversion in code, never in a prompt. Unknown pairs raise instead of guessing."""

from __future__ import annotations

from decimal import Decimal

KG_PER_LB = Decimal("0.45359237")

_RATIOS: dict[tuple[str, str], Decimal] = {
    ("kWh", "kWh"): Decimal(1),
    ("MWh", "kWh"): Decimal(1000),
    ("kWh", "MWh"): Decimal("0.001"),
    ("L", "L"): Decimal(1),
    ("kgCO2e", "kgCO2e"): Decimal(1),
    ("kgCO2e", "tCO2e"): Decimal("0.001"),
    ("tCO2e", "kgCO2e"): Decimal(1000),
    ("tCO2e", "tCO2e"): Decimal(1),
}

KNOWN_FACTOR_UNITS = {"kgCO2e/kWh", "kgCO2e/L"}


class UnsupportedUnit(ValueError):
    """A conversion that is not in the table; add it deliberately rather than falling back."""


def convert(value: Decimal, from_unit: str, to_unit: str) -> Decimal:
    """Convert ``value`` between two units from the table above."""
    try:
        return value * _RATIOS[(from_unit, to_unit)]
    except KeyError:
        raise UnsupportedUnit(f"no conversion from {from_unit!r} to {to_unit!r}") from None


def denominator(factor_unit: str) -> str:
    """Return the activity unit a factor unit expects, e.g. ``kgCO2e/kWh`` -> ``kWh``."""
    if factor_unit not in KNOWN_FACTOR_UNITS:
        raise UnsupportedUnit(f"unknown factor unit {factor_unit!r}")
    return factor_unit.split("/", 1)[1]


def lb_per_mwh_to_kg_per_kwh(value: Decimal) -> Decimal:
    """eGRID publishes lb/MWh; factors here are kgCO2e/kWh."""
    return value * KG_PER_LB / Decimal(1000)


def g_per_kwh_to_kg_per_kwh(value: Decimal) -> Decimal:
    """Ember publishes gCO2e/kWh; factors here are kgCO2e/kWh."""
    return value / Decimal(1000)
