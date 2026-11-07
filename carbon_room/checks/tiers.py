"""Tier-1 automatic verification requires matching baseline factor and small variance."""

from datetime import date
from decimal import Decimal

from carbon_room.ledger import ledger


def tier1_ok(ctx, claim) -> tuple[bool, str]:
    source = next((item for item in ctx.sources if item.source_doc_id == claim.source_doc_id), None)
    if source is None or source.extract_status != "OK":
        return False, "source evidence is missing"
    year, month = map(int, claim.month.split("-"))
    previous = date(year - (month == 1), (month - 2) % 12 + 1, 1).strftime("%Y-%m")
    baseline = [
        item for item in ctx.claims if (item.site, item.activity, item.month) == (claim.site, claim.activity, previous)
    ]
    if len(baseline) != 1:
        return False, "one previous-month baseline is required"
    current_calc = ledger.latest_calculation(ctx.conn, claim.claim_id)
    baseline_calc = ledger.latest_calculation(ctx.conn, baseline[0].claim_id)
    if current_calc is None or baseline_calc is None or current_calc.factor_version != baseline_calc.factor_version:
        return False, "factor version differs from the previous month"
    variance = abs(claim.value - baseline[0].value) / baseline[0].value
    maximum = Decimal(str(ctx.settings["approvals"]["tier1"]["max_variance"]))
    if variance >= maximum:
        return False, f"variance {variance * 100:.0f}% ≥ {maximum * 100:.0f}%"
    return True, "same factor version, source present, variance below tier-1 threshold"
