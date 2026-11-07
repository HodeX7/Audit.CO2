"""R3: selected factor outside the close's locked edition or age policy."""

from decimal import Decimal

from carbon_room.calc import factors
from carbon_room.checks.framework import make_finding
from carbon_room.ledger import ledger
from carbon_room.models import Option


def rule(ctx):
    results = []
    for claim in ctx.current:
        calc = ctx.calc(claim, "location" if claim.activity == "dc_it_kwh" else None)
        if calc is None:
            continue
        factor = ledger.get_factor(ctx.conn, calc.factor_id)
        stale, reason = factors.is_stale(ctx.close, factor)
        if not stale:
            continue
        locked = factors.locked_factor(ctx.conn, ctx.close, claim.site, claim.activity)
        difference = abs(Decimal(factor["value"]) - Decimal(locked["value"])) * claim.value
        if claim.activity == "dc_it_kwh":
            difference *= Decimal(str(claim.attributes["pue"]))
        results.append(
            make_finding(
                "R3",
                "STALE",
                [claim.claim_id],
                claim.site,
                claim.month,
                ctx.lead,
                f"{claim.site} uses stale factor {factor['factor_id']}",
                [reason, f"Locked factor: {locked['factor_id']}; difference: {difference / 1000} tCO2e"],
                [
                    Option("approve", "approve", f"Use {locked['factor_id']}", {"use_factor_id": locked["factor_id"]}),
                    Option("reject", "reject", "Exclude this claim"),
                ],
                2,
                True,
            )
        )
    return results
