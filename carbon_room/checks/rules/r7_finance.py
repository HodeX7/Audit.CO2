"""R7: optional tariff check when an invoice exposes price and currency."""

from decimal import Decimal

from carbon_room.checks.framework import make_finding
from carbon_room.models import Option


def rule(ctx):
    band = ctx.settings.get("finance", {}).get("tariff_band")
    if not band:
        return []
    results = []
    for claim in ctx.current:
        amount, currency = claim.attributes.get("amount"), claim.attributes.get("currency")
        if amount is None or not currency:
            continue
        tariff = Decimal(str(amount)) / claim.value
        minimum, maximum = Decimal(str(band["min"])), Decimal(str(band["max"]))
        if minimum <= tariff <= maximum:
            continue
        results.append(
            make_finding(
                "R7",
                "FINANCE",
                [claim.claim_id],
                claim.site,
                claim.month,
                ctx.settings.get("finance", {}).get("owner", "finance"),
                f"{claim.site} tariff is outside the configured band",
                [f"{amount} {currency} / {claim.value} {claim.unit} = {tariff} {currency}/{claim.unit}"],
                [Option("approve", "approve", "Approve the tariff"), Option("reject", "reject", "Exclude this claim")],
                2,
                False,
            )
        )
    return results
