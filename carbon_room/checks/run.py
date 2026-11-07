"""Run deterministic rules, persist actionable gaps, then verify live claims."""

from __future__ import annotations

from carbon_room.actors import WATCHDOG
from carbon_room.calc import factors
from carbon_room.checks.framework import CheckContext
from carbon_room.checks.rules import RULES
from carbon_room.checks.tiers import tier1_ok
from carbon_room.ledger import ledger


def _merge_period_missing(findings):
    periods = {(item.site, item.month): item for item in findings if item.rule == "R4"}
    merged = []
    for finding in findings:
        if finding.rule == "R1" and (finding.site, finding.month) in periods:
            periods[(finding.site, finding.month)].evidence.extend(finding.evidence)
            periods[(finding.site, finding.month)].evidence.append("Expected current-month source is missing")
            continue
        merged.append(finding)
    return merged


def _verify(ctx, findings, gaps):
    open_ids = {gap.finding_id for gap in gaps}
    blocking = {
        claim_id
        for finding in findings
        if finding.blocking and finding.finding_id in open_ids
        for claim_id in finding.claim_ids
    }
    priorities = {"CONFLICTING": 3, "STALE": 2}
    for claim in ctx.current:
        calc = (
            ledger.latest_calculation(ctx.conn, claim.claim_id, "location")
            if claim.activity == "dc_it_kwh"
            else ledger.latest_calculation(ctx.conn, claim.claim_id)
        )
        locked = calc is not None and factors.is_locked(ctx.close, ledger.get_factor(ctx.conn, calc.factor_id))
        decisions = [item["decision"] for item in ctx.approvals if item["subject_id"] == claim.claim_id]
        decision = decisions[-1] if decisions else None
        approved = decision == "approve"
        rejected = decision == "reject"
        tier_one, reason = tier1_ok(ctx, claim)
        verified = locked and claim.claim_id not in blocking and not rejected and (tier_one or approved)
        if verified:
            status = "VERIFIED"
        else:
            relevant = [
                finding.kind
                for finding in findings
                if finding.finding_id in open_ids and claim.claim_id in finding.claim_ids
            ]
            status = max(relevant, key=lambda item: priorities.get(item, 1)) if relevant else "UNVERIFIED"
            if status not in ("CONFLICTING", "STALE"):
                status = "UNVERIFIED"
        if status != claim.status:
            ledger.set_status(ctx.conn, claim.claim_id, status, WATCHDOG, reason if verified else "Watchdog check")


def check(conn, close_id):
    """Return current findings and make an unchanged second invocation write no events."""
    ctx = CheckContext.load(conn, close_id)
    if ctx.close["phase"] == "PUBLISHED":
        raise ValueError("published close cannot be rechecked; start a new version")
    findings = _merge_period_missing([finding for rule in RULES for finding in rule(ctx)])
    actionable = [finding for finding in findings if finding.options or finding.blocking]
    current_ids = {finding.finding_id for finding in actionable}
    previous = {gap.finding_id: gap for gap in ledger.get_gaps(conn, close_id, status="OPEN")}
    new_findings = any(finding.finding_id not in previous for finding in actionable)
    stale_gaps = [gap for key, gap in previous.items() if key not in current_ids]
    desired_open = bool(current_ids)
    phase = ctx.close["phase"]
    final_phase = "AWAITING_HUMANS" if desired_open else "CHECKING"
    if new_findings or stale_gaps or phase != final_phase:
        if phase not in ("CHECKING", "AWAITING_HUMANS"):
            ledger.set_phase(conn, close_id, "CHECKING", WATCHDOG)
        for gap in stale_gaps:
            ledger.resolve_gap(conn, close_id, gap.gap_id, WATCHDOG, None, {"outcome": "cleared_by_recheck"})
        for finding in actionable:
            ledger.upsert_gap(conn, close_id, finding)
    gaps = ledger.get_gaps(conn, close_id, status="OPEN")
    _verify(ctx, findings, gaps)
    final_phase = "AWAITING_HUMANS" if gaps else "CHECKING"
    if ledger.get_close(conn, close_id)["phase"] != final_phase:
        ledger.set_phase(conn, close_id, final_phase, WATCHDOG)
    return findings
