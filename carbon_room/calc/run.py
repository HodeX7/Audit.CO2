"""calculate(): price every live claim of a close and record the result in the ledger."""

from __future__ import annotations

from carbon_room.actors import CALCULATOR
from carbon_room.calc import factors
from carbon_room.calc.calculator import compute
from carbon_room.ledger import ledger
from carbon_room.models import Calculation, Claim


def choose_factor(conn, close: dict, claim: Claim) -> dict:
    """A factor already set on the claim wins (a human may have switched it); otherwise the locked set decides."""
    if claim.factor_id:
        return ledger.get_factor(conn, claim.factor_id)
    return factors.locked_factor(conn, close, claim.site, claim.activity)


def calculate(conn, close_id: str) -> list[Calculation]:
    """Calculate every live non-data-centre claim, both months, so the prior month can serve as a baseline.

    Safe to re-run: a claim whose factor, quantity and result are unchanged gets no new calculation and no event.
    """
    close = ledger.get_close(conn, close_id)
    if close["phase"] in ("OPEN", "COLLECTING"):
        ledger.set_phase(conn, close_id, "CALCULATING", CALCULATOR)
    results: list[Calculation] = []
    for claim in ledger.get_claims(conn, close_id):
        if claim.activity == "dc_it_kwh":
            continue
        factor = choose_factor(conn, close, claim)
        if claim.factor_id != factor["factor_id"]:
            ledger.set_factor(conn, claim.claim_id, factor["factor_id"], factor["version"], CALCULATOR,
                              "factor chosen at calculation")
            claim = ledger.get_claim(conn, claim.claim_id)
        fresh = compute(claim, factor)
        latest = ledger.latest_calculation(conn, claim.claim_id)
        unchanged = (latest is not None and latest.factor_id == fresh.factor_id
                     and latest.activity_value == fresh.activity_value and latest.kgco2e == fresh.kgco2e)
        if not unchanged:
            ledger.add_calculation(conn, fresh)
            latest = ledger.latest_calculation(conn, claim.claim_id)
        results.append(latest)
    return results
