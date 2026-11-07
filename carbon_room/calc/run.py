"""calculate(): price every live claim of a close and record the result in the ledger."""

from __future__ import annotations

from carbon_room.actors import CALCULATOR
from carbon_room.calc import factors
from carbon_room.calc.calculator import compute
from carbon_room.calc.datacentre import compute as compute_datacentre
from carbon_room.ledger import ledger
from carbon_room.models import Calculation, Claim


def choose_factor(conn, close: dict, claim: Claim) -> dict:
    """Pick the factor for a claim.

    A factor already on the claim (a human may have switched it) is honoured only if it is for the claim's activity
    and comes from the source and geography the site's config prescribes. Its version may differ: an older edition
    is priced as it is, and the stale-factor rule decides whether that is acceptable. Otherwise the locked set decides.
    """
    if claim.factor_id:
        factor = ledger.get_factor(conn, claim.factor_id)
        factors.ensure_allowed(claim.site, claim.activity, factor)
        return factor
    vendor_ref = claim.attributes.get("vendor_factor_ref")
    if vendor_ref:
        factor = factors.factor_from_ref(conn, vendor_ref)
        factors.ensure_allowed(claim.site, claim.activity, factor)
        return factor
    return factors.locked_factor(conn, close, claim.site, claim.activity)


def calculate(conn, close_id: str) -> list[Calculation]:
    """Calculate every live claim, including previous-month baselines.

    Safe to re-run: a claim whose factor, quantity and result are unchanged gets no new calculation and no event.
    """
    close = ledger.get_close(conn, close_id)
    if close["phase"] == "PUBLISHED":
        raise ValueError("published close cannot be recalculated; start a new version")
    if close["phase"] in ("OPEN", "COLLECTING"):
        ledger.set_phase(conn, close_id, "CALCULATING", CALCULATOR)
    results: list[Calculation] = []
    for claim in ledger.get_claims(conn, close_id):
        factor = choose_factor(conn, close, claim)
        if claim.factor_id != factor["factor_id"]:
            ledger.set_factor(
                conn, claim.claim_id, factor["factor_id"], factor["version"], CALCULATOR, "factor chosen at calculation"
            )
            claim = ledger.get_claim(conn, claim.claim_id)
        candidates = compute_datacentre(claim, factor) if claim.activity == "dc_it_kwh" else [compute(claim, factor)]
        for fresh in candidates:
            latest = ledger.latest_calculation(conn, claim.claim_id, fresh.basis)
            unchanged = latest is not None and all(
                getattr(latest, field) == getattr(fresh, field)
                for field in (
                    "factor_id",
                    "factor_version",
                    "activity_value",
                    "activity_unit",
                    "factor_value",
                    "factor_unit",
                    "kgco2e",
                    "formula",
                    "basis",
                )
            )
            if not unchanged:
                ledger.add_calculation(conn, fresh)
                latest = ledger.latest_calculation(conn, claim.claim_id, fresh.basis)
            results.append(latest)
    return results
