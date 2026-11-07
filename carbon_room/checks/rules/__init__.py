"""Registered deterministic Watchdog rules."""

from carbon_room.checks.rules import (
    r1_missing,
    r2_conflict,
    r3_stale,
    r4_period,
    r5_variance,
    r6_datacentre,
    r7_finance,
)

RULES = (
    r1_missing.rule,
    r2_conflict.rule,
    r3_stale.rule,
    r4_period.rule,
    r5_variance.rule,
    r6_datacentre.rule,
    r7_finance.rule,
)
