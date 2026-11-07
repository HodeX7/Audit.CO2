"""R2: disagreeing live claims for the same site, month and activity."""

from collections import defaultdict
from decimal import Decimal

from carbon_room.checks.framework import make_finding
from carbon_room.models import Option


def rule(ctx):
    groups = defaultdict(list)
    for claim in ctx.current:
        groups[(claim.site, claim.month, claim.activity)].append(claim)
    results = []
    tolerance = Decimal(str(ctx.settings["rules"]["conflict_tolerance"]))
    for (site, month, activity), claims in sorted(groups.items()):
        if len(claims) < 2:
            continue
        minimum, maximum = min(claim.value for claim in claims), max(claim.value for claim in claims)
        if minimum <= 0 or (maximum - minimum) / minimum <= tolerance:
            continue
        claims.sort(key=lambda claim: claim.claim_id)
        options = [
            Option(
                f"pick {chr(65 + index)}",
                "pick",
                f"{claim.claim_id}: {claim.source_excerpt}",
                {
                    "claim_id": claim.claim_id,
                },
            )
            for index, claim in enumerate(claims)
        ]
        results.append(
            make_finding(
                "R2",
                "CONFLICTING",
                [claim.claim_id for claim in claims],
                site,
                month,
                ctx.lead,
                f"Conflicting {activity} evidence for {site}",
                [claim.source_excerpt for claim in claims] + [f"Difference: {maximum - minimum} {claims[0].unit}"],
                options,
                2,
                True,
            )
        )
    return results
