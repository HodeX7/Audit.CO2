"""R1: expected source/activity pairs with no current-month live claim."""

from carbon_room import config
from carbon_room.checks.framework import make_finding
from carbon_room.models import Option


def rule(ctx):
    results = []
    for site, kind, activity in config.expected_sources(ctx.close["month"]):
        if site not in ctx.close["sites"]:
            continue
        if any(claim.site == site and claim.activity == activity for claim in ctx.current):
            continue
        failed = [source for source in ctx.sources if source.site == site and source.extract_status == "FAILED"]
        evidence = [f"{source.file_name} could not be read: {source.extract_error}" for source in failed]
        results.append(
            make_finding(
                "R1",
                "MISSING",
                [],
                site,
                ctx.close["month"],
                ctx.owner(site),
                f"{site} {activity} is missing for {ctx.close['month']}",
                evidence or ["No current-period claim"],
                [
                    Option(
                        "upload",
                        "upload",
                        "Upload the current-period evidence",
                        {
                            "site": site,
                            "month": ctx.close["month"],
                            "activity": activity,
                        },
                    )
                ],
                2,
                True,
            )
        )
    return results
