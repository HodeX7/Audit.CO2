"""Read-only close totals and coverage, derived from the authoritative ledger."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from carbon_room import config
from carbon_room.ledger import ledger
from carbon_room.models import CloseSummary, DcLine

REC_ZERO = "Market-based 0 relies on certificates; certificate quality not verified"


def _dc_line(conn, claims):
    dc_claims = [claim for claim in claims if claim.activity == "dc_it_kwh"]
    if not dc_claims:
        return None
    location = [ledger.latest_calculation(conn, claim.claim_id, "location") for claim in dc_claims]
    market = [ledger.latest_calculation(conn, claim.claim_id, "market") for claim in dc_claims]
    pue_values = set()
    for claim in dc_claims:
        raw = claim.attributes.get("pue")
        if raw is not None:
            try:
                value = Decimal(str(raw))
                if value.is_finite() and value > 0:
                    pue_values.add(value)
            except InvalidOperation:
                pass
    pue = next(iter(pue_values)) if len(pue_values) == 1 else None
    markets = [item for item in market if item is not None]
    zero_certificates = any(item.kgco2e == 0 for item in markets)
    note = "Vendor has not supplied per-model AI workload data; AI line is unverified."
    if pue is None:
        note += " PUE is missing or inconsistent."
    return DcLine(
        sum((item.kgco2e for item in location if item is not None), Decimal(0)) if any(location) else None,
        sum((item.kgco2e for item in markets), Decimal(0)) if markets else None,
        pue,
        REC_ZERO if zero_certificates else "",
        "UNVERIFIED",
        note,
    )


def build(conn, close_id: str) -> CloseSummary:
    """Read one close without changing its phase, audit chain or calculated amounts."""
    close = ledger.get_close(conn, close_id)
    claims = ledger.get_claims(conn, close_id, month=close["month"])
    verified = Decimal(0)
    excluded = Decimal(0)
    for claim in claims:
        calculation = (
            ledger.latest_calculation(conn, claim.claim_id, "location")
            if claim.activity == "dc_it_kwh"
            else ledger.latest_calculation(conn, claim.claim_id)
        )
        if calculation is None:
            continue
        if claim.status == "VERIFIED":
            verified += calculation.kgco2e
        else:
            excluded += calculation.kgco2e
    denominator = verified + excluded
    coverage = (
        (verified / denominator * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP) if denominator else Decimal(0)
    )
    expected = [entry for entry in config.expected_sources(close["month"]) if entry[0] in close["sites"]]
    present = {(claim.site, claim.activity) for claim in claims if claim.status == "VERIFIED"}
    sources_verified = sum((site, activity) in present for site, _kind, activity in expected)
    return CloseSummary(
        close_id,
        close["phase"],
        verified,
        excluded,
        coverage,
        len(expected),
        sources_verified,
        ledger.get_gaps(conn, close_id, status="OPEN"),
        _dc_line(conn, claims),
    )
