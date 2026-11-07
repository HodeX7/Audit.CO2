"""Pure emissions arithmetic: activity x factor, in Decimal, with every step written into the formula.

No database, no clock, no model. The same inputs always give the same Calculation, which is what lets the Reporter
recompute any published number for an auditor. Data-centre claims are priced separately (they need a PUE).
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from carbon_room.calc import units
from carbon_room.models import Calculation, Claim


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def basis_of(claim: Claim) -> str | None:
    """Purchased electricity is location-based; fuel has no basis."""
    return "location" if claim.activity == "electricity_kwh" else None


def compute(claim: Claim, factor: dict) -> Calculation:
    """Multiply a claim's activity by a factor row. ``calc_id`` is left empty for the ledger to assign."""
    if claim.activity == "dc_it_kwh":
        raise ValueError("data-centre claims need a PUE and are priced by the data-centre calculation")
    if not claim.value.is_finite() or claim.value <= 0:
        raise ValueError("activity value must be a positive finite Decimal")
    factor_value = Decimal(factor["value"])
    if not factor_value.is_finite() or factor_value <= 0:
        raise ValueError("factor value must be a positive finite Decimal")
    unit = units.denominator(factor["unit"])
    quantity = units.convert(claim.value, claim.unit, unit)
    with localcontext() as context:
        context.prec = 50
        kg = quantity * factor_value
    formula = f"{_text(quantity)} {unit} × {_text(factor_value)} {factor['unit']} = {_text(kg)} kgCO2e"
    return Calculation(
        "",
        claim.claim_id,
        factor["factor_id"],
        factor["version"],
        claim.value,
        claim.unit,
        factor_value,
        factor["unit"],
        kg,
        formula,
        basis_of(claim),
    )


def recompute(calc: Calculation, claim: Claim, factor: dict) -> tuple[str, Decimal, bool]:
    """Run the calculation again from stored inputs; ``matches`` is exact equality with what was stored."""
    if claim.activity == "dc_it_kwh":
        from carbon_room.calc.datacentre import compute as compute_datacentre

        candidates = compute_datacentre(claim, factor)
        fresh = next((candidate for candidate in candidates if candidate.basis == calc.basis), None)
        if fresh is None:
            raise ValueError(f"data-centre basis {calc.basis!r} has no source value")
    else:
        fresh = compute(claim, factor)
    same = (
        fresh.factor_id == calc.factor_id
        and fresh.factor_version == calc.factor_version
        and fresh.activity_value == calc.activity_value
        and fresh.activity_unit == calc.activity_unit
        and fresh.factor_value == calc.factor_value
        and fresh.factor_unit == calc.factor_unit
        and fresh.kgco2e == calc.kgco2e
        and fresh.formula == calc.formula
        and fresh.basis == calc.basis
    )
    return fresh.formula, fresh.kgco2e, same
