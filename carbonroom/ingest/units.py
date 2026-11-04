"""Unit normalization for activity data.

Canonical units (what the ledger stores):
  electricity   -> kWh
  cloud_compute -> kWh   (IT equipment energy)
  natural_gas   -> therm
  diesel        -> gal   (US gallon)
  REC / PPA     -> MWh   (instruments table)

Conversions are exact by definition:
  1 MWh = 1,000 kWh
  1 dekatherm (Dth) = 10 therms; 1 MMBtu = 10 therms (1 therm = 100,000 Btu)
  1 US gallon = 3.785411784 litres (exact; NIST Handbook 44, Appendix C)

Litres -> gallons is the only inexact step; it is rounded to 0.001 gal (ROUND_HALF_EVEN)
and the original quantity and unit are always kept in extra_json.
Volume units for gas (ccf, m3) are NOT converted: that needs the utility's heat content,
so they are rejected and become a gap instead of a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

US_GALLON_L = Decimal("3.785411784")

# canonical unit -> spellings found on documents (matched case-insensitively as whole tokens)
UNIT_ALIASES: dict[str, tuple[str, ...]] = {
    "kWh": ("kwh", "kilowatt-hours", "kilowatt hours", "kilowatt-hour", "kilowatt hour"),
    "MWh": ("mwh", "megawatt-hours", "megawatt hours", "megawatt-hour", "megawatt hour"),
    "therm": ("therm", "therms", "thm"),
    "Dth": ("dth", "dekatherm", "dekatherms", "decatherm", "decatherms"),
    "MMBtu": ("mmbtu",),
    "gal": ("gal", "gals", "gallon", "gallons", "us gal", "us gallons"),
    "L": ("l", "litre", "litres", "liter", "liters"),
    "L/kWh": ("l/kwh", "litres/kwh", "liters/kwh", "litres per kwh", "liters per kwh"),
}

CATEGORY_UNITS: dict[str, dict[str, Decimal | str]] = {
    # category -> {source canonical unit: multiplier into target unit}; "target" names the unit
    "electricity": {"target": "kWh", "kWh": Decimal(1), "MWh": Decimal(1000)},
    "cloud_compute": {"target": "kWh", "kWh": Decimal(1), "MWh": Decimal(1000)},
    "natural_gas": {"target": "therm", "therm": Decimal(1), "Dth": Decimal(10), "MMBtu": Decimal(10)},
    "diesel": {"target": "gal", "gal": Decimal(1), "L": "litres"},
    "rec_mwh": {"target": "MWh", "MWh": Decimal(1), "kWh": Decimal("0.001")},
}

KNOWN_CATEGORIES = ("electricity", "natural_gas", "diesel", "cloud_compute")


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class Normalized:
    quantity: Decimal
    unit: str
    original_quantity: str
    original_unit: str
    conversion: str


def canonical_unit(text: str) -> str | None:
    """'kilowatt hours' -> 'kWh'; unknown -> None."""
    key = " ".join(text.strip().lower().replace(".", "").split())
    for canon, aliases in UNIT_ALIASES.items():
        if key == canon.lower() or key in aliases:
            return canon
    return None


def unit_in_text(unit: str, text: str) -> bool:
    """True if any spelling of `unit` appears in `text` as a whole token."""
    canon = canonical_unit(unit)
    if canon is None:
        return False
    for alias in (canon.lower(), *UNIT_ALIASES[canon]):
        pattern = r"(?<![A-Za-z/])" + re.escape(alias) + r"(?![A-Za-z/])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def normalize(category: str, quantity: Decimal, unit: str) -> Normalized:
    """Convert a printed quantity into the ledger's canonical unit for `category`."""
    table = CATEGORY_UNITS.get(category)
    if table is None:
        raise UnitError(f"unknown category {category!r}")
    canon = canonical_unit(unit)
    if canon is None or canon not in table:
        raise UnitError(f"unit {unit!r} can't be converted for {category} without an assumption")
    target = str(table["target"])
    factor = table[canon]
    if factor == "litres":
        q = (quantity / US_GALLON_L).quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
        conversion = "L / 3.785411784 = US gal (rounded to 0.001)"
    else:
        q = quantity * Decimal(factor)
        conversion = "none" if factor == 1 else f"{canon} x {factor} = {target}"
    return Normalized(q, target, str(quantity), canon, conversion)
