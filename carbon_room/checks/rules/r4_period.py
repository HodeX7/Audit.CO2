"""R4: source-labelled month disagrees with the printed billing period."""

import re
from datetime import date, timedelta
from decimal import Decimal

from carbon_room.checks.framework import make_finding
from carbon_room.models import Option
from carbon_room.sources.period import parse_period


def _overlap(start: date, end: date, month: str) -> Decimal:
    year, month_number = map(int, month.split("-"))
    first = date(year, month_number, 1)
    last = date(year + (month_number == 12), month_number % 12 + 1, 1) - timedelta(days=1)
    days = (end - start).days + 1
    if days <= 0:
        return Decimal(0)
    shared = max(0, (min(end, last) - max(start, first)).days + 1)
    return Decimal(shared) / Decimal(days)


def rule(ctx):
    results = []
    for source in ctx.sources:
        if source.site not in ctx.close["sites"] or source.extract_status != "OK":
            continue
        label = re.search(r"(?<!\d)(\d{4}-\d{2})(?!\d)", source.file_name)
        if label is None or label.group(1) != ctx.close["month"]:
            continue
        period = parse_period(source.raw_text)
        if period is None or _overlap(
            date.fromisoformat(period[0]), date.fromisoformat(period[1]), ctx.close["month"]
        ) >= Decimal(str(ctx.settings["rules"]["period_min_overlap"])):
            continue
        claims = [claim for claim in ctx.claims if claim.source_doc_id == source.source_doc_id]
        if not claims:
            continue
        activity = claims[0].activity
        results.append(
            make_finding(
                "R4",
                "PERIOD",
                [claim.claim_id for claim in claims],
                source.site,
                ctx.close["month"],
                ctx.owner(source.site),
                f"{source.site} bill is labelled {ctx.close['month']} but covers {period[0]} to {period[1]}",
                [f"{source.file_name}: printed period {period[0]} to {period[1]}"],
                [
                    Option(
                        "upload",
                        "upload",
                        "Upload the correct-period bill",
                        {
                            "site": source.site,
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
