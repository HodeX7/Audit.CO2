"""Unit conversions for activity quantities.

Factor units (see data/factors/*.csv) are fixed per category:
  natural_gas -> kg_co2e_per_mmbtu
  diesel      -> kg_co2e_per_gallon
  electricity / cloud_compute -> kg_co2e_per_kwh or kg_co2_per_kwh

An activity row can arrive in a different but common bill unit (e.g. therms
instead of mmBtu). These helpers convert the activity's recorded quantity
into the unit the factor expects, so the Calculator never has to guess.
"""

from decimal import Decimal


class UnsupportedUnitError(ValueError):
    """Raised when an activity's unit has no known conversion for its category."""


# 1 therm = 100,000 BTU = 0.1 mmBtu (US DOE / EPA convention).
_NATURAL_GAS_TO_MMBTU = {
    "mmbtu": Decimal("1"),
    "therms": Decimal("0.1"),
    "therm": Decimal("0.1"),
}

_DIESEL_TO_GALLON = {
    "gallon": Decimal("1"),
    "gallons": Decimal("1"),
}

# Electricity and cloud_compute are both billed/metered in kWh in our seed
# data; MWh is supported since RECs/instruments are recorded in MWh.
_ELECTRICITY_TO_KWH = {
    "kwh": Decimal("1"),
    "mwh": Decimal("1000"),
}


def to_mmbtu(quantity: Decimal, unit: str) -> Decimal:
    key = unit.strip().lower()
    if key not in _NATURAL_GAS_TO_MMBTU:
        raise UnsupportedUnitError(f"no mmBtu conversion for natural_gas unit '{unit}'")
    return quantity * _NATURAL_GAS_TO_MMBTU[key]


def to_gallons(quantity: Decimal, unit: str) -> Decimal:
    key = unit.strip().lower()
    if key not in _DIESEL_TO_GALLON:
        raise UnsupportedUnitError(f"no gallon conversion for diesel unit '{unit}'")
    return quantity * _DIESEL_TO_GALLON[key]


def to_kwh(quantity: Decimal, unit: str) -> Decimal:
    key = unit.strip().lower()
    if key not in _ELECTRICITY_TO_KWH:
        raise UnsupportedUnitError(f"no kWh conversion for electricity unit '{unit}'")
    return quantity * _ELECTRICITY_TO_KWH[key]
