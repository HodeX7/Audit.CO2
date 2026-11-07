"""R6: data-centre calculation completeness and unverified AI attribution."""

from carbon_room.checks.framework import make_finding
from carbon_room.models import Option

AI_TITLE = "AI workload has no per-model data from the vendor; AI line stays UNVERIFIED"


def rule(ctx):
    results = []
    for claim in ctx.current:
        if claim.activity != "dc_it_kwh":
            continue
        if ctx.calc(claim, "location") is None:
            results.append(
                make_finding(
                    "R6",
                    "DATACENTRE",
                    [claim.claim_id],
                    claim.site,
                    claim.month,
                    ctx.owner(claim.site),
                    f"{claim.site} has no data-centre location calculation",
                    [claim.source_excerpt],
                    [
                        Option(
                            "upload",
                            "upload",
                            "Upload complete data-centre evidence",
                            {
                                "site": claim.site,
                                "month": claim.month,
                                "activity": claim.activity,
                            },
                        )
                    ],
                    2,
                    True,
                )
            )
            continue
        if not claim.attributes.get("ai_breakdown_available"):
            results.append(
                make_finding(
                    "R6",
                    "DATACENTRE",
                    [claim.claim_id],
                    claim.site,
                    claim.month,
                    ctx.lead,
                    AI_TITLE,
                    ["Vendor source has no per-model AI workload breakdown"],
                    [],
                    2,
                    False,
                )
            )
    return results
