"""Tier 1 checks source, matched factor edition and strict variance threshold."""

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks.framework import CheckContext
from carbon_room.checks.tiers import tier1_ok


def test_seed_diesel_is_tier_one_but_hq_electricity_needs_review(factor_db, close_id):
    collect.ingest(factor_db, close_id, CALCULATOR)
    calc_run.calculate(factor_db, close_id)
    ctx = CheckContext.load(factor_db, close_id)
    diesel = next(
        claim for claim in ctx.current if claim.site == "hq" and claim.activity == "diesel_l" and claim.value == 2400
    )
    electricity = next(claim for claim in ctx.current if claim.site == "hq" and claim.activity == "electricity_kwh")
    assert tier1_ok(ctx, diesel)[0]
    assert tier1_ok(ctx, electricity) == (False, "variance 38% ≥ 10%")
