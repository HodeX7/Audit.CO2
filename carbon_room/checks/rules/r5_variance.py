"""R5: current-period activity differs materially from the previous month."""

from datetime import date
from decimal import Decimal

from carbon_room.checks.framework import make_finding
from carbon_room.models import Option


def rule(ctx):
    year, month = map(int, ctx.close["month"].split("-"))
    previous = date(year - (month == 1), (month - 2) % 12 + 1, 1).strftime("%Y-%m")
    threshold = Decimal(str(ctx.settings["rules"]["variance_threshold"]))
    results = []
    for claim in ctx.current:
        baseline = [
            item
            for item in ctx.claims
            if (item.site, item.activity, item.month) == (claim.site, claim.activity, previous)
        ]
        if len(baseline) != 1 or baseline[0].value <= 0:
            continue
        variance = abs(claim.value - baseline[0].value) / baseline[0].value
        if variance < threshold:
            continue
        percentage = variance * 100
        results.append(
            make_finding(
                "R5",
                "VARIANCE",
                [claim.claim_id],
                claim.site,
                claim.month,
                ctx.lead,
                f"{claim.site} {claim.activity} changed by {percentage}%",
                [
                    f"{baseline[0].value} {claim.unit} in {previous}; {claim.value} {claim.unit} in {claim.month}",
                    f"Variance {percentage}% ≥ {threshold * 100}%",
                ],
                [
                    Option("approve", "approve", "Approve the variance"),
                    Option("reject", "reject", "Exclude this claim"),
                ],
                2,
                True,
            )
        )
    return results
