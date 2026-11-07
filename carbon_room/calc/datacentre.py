"""Deterministic location and vendor-reported market calculations for cloud evidence."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from carbon_room.calc import units
from carbon_room.calc.calculator import _text
from carbon_room.models import Calculation, Claim


def _decimal(value: object, name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"{name} must be a finite Decimal") from error
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"{name} must be a {'nonnegative' if allow_zero else 'positive'} finite Decimal")
    return number


def compute(claim: Claim, factor: dict) -> list[Calculation]:
    """Return a location calculation plus a market record only when the vendor supplied one."""
    if claim.activity != "dc_it_kwh":
        raise ValueError("data-centre computation requires dc_it_kwh")
    quantity = _decimal(claim.value, "IT energy")
    if "pue" not in claim.attributes:
        raise ValueError("PUE is missing from data-centre evidence")
    pue = _decimal(claim.attributes["pue"], "PUE")
    factor_value = _decimal(factor["value"], "factor value")
    unit = units.denominator(factor["unit"])
    energy = units.convert(quantity, claim.unit, unit)
    with localcontext() as context:
        context.prec = 50
        location_kg = energy * pue * factor_value
    location = Calculation(
        "",
        claim.claim_id,
        factor["factor_id"],
        factor["version"],
        quantity,
        claim.unit,
        factor_value,
        factor["unit"],
        location_kg,
        f"{_text(energy)} {unit} × PUE {_text(pue)} × {_text(factor_value)} {factor['unit']} "
        f"= {_text(location_kg)} kgCO2e",
        "location",
    )
    results = [location]
    reported = claim.attributes.get("market_based_kgco2e")
    if reported is not None:
        market_kg = _decimal(reported, "market-based kgCO2e", allow_zero=True)
        results.append(
            Calculation(
                "",
                claim.claim_id,
                factor["factor_id"],
                factor["version"],
                quantity,
                claim.unit,
                factor_value,
                factor["unit"],
                market_kg,
                "as reported by vendor (certificates)",
                "market",
            )
        )
    return results
