"""The Checker/Watchdog orchestrator: runs every rule in rules.py for one
period, drops any gap whose dedupe_key already exists (idempotency), and
merges the status updates each rule proposed using a fixed precedence.

This module still does not touch a database. It takes the current ledger
state as plain dicts/lists and returns a CheckResult describing what
*should* change. The caller (CLI / db layer, once it exists) is the only
thing that actually writes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from . import rules
from .rules import GapCandidate

# CONFLICTING beats FLAGGED beats leaving it alone. Checker never sets
# VERIFIED here — that only happens when every check for an activity is
# clean (see `promote_clean_activities`).
_STATUS_PRECEDENCE = {"CONFLICTING": 2, "FLAGGED": 1}


@dataclass
class CheckResult:
    new_gaps: list[dict] = field(default_factory=list)
    status_updates: dict[str, str] = field(default_factory=dict)      # activity_id -> status
    instrument_updates: dict[str, str] = field(default_factory=dict)  # instrument_id -> quality_flags
    events: list[dict] = field(default_factory=list)
    # gap_id -> the activity ids it concerns. Not part of the shared `gaps`
    # table (contracts/schema.sql) -- callers that persist gaps (e.g. the
    # CLI's db.py) use this to know what a later `resolve` should target.
    gap_activity_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _gap_id(dedupe_key: str) -> str:
    return f"gap-{hashlib.sha256(dedupe_key.encode()).hexdigest()[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_gap_row(candidate: GapCandidate) -> dict:
    return {
        "id": _gap_id(candidate.dedupe_key),
        "period_id": candidate.period_id,
        "site_id": candidate.site_id,
        "kind": candidate.kind,
        "detail": candidate.detail,
        "owner_handle": candidate.owner_handle,
        "room": candidate.room,
        "thread_id": None,
        "status": "OPEN",
        "resolution": None,
        "resolved_by": None,
        "resolved_at": None,
        "created_at": _now_iso(),
        "dedupe_key": candidate.dedupe_key,
    }


def _merge_status(into: dict[str, str], updates: dict[str, str]) -> None:
    for activity_id, new_status in updates.items():
        current = into.get(activity_id)
        if current is None or _STATUS_PRECEDENCE.get(new_status, 0) > _STATUS_PRECEDENCE.get(current, 0):
            into[activity_id] = new_status


def run_checks(
    *,
    period_id: str,
    sites: list[dict],
    periods: list[dict],
    activities: list[dict],
    prior_period_activities: list[dict],
    source_docs: list[dict],
    calculations: list[dict],
    factors: list[dict],
    instruments: list[dict],
    existing_gaps: list[dict],
    expected_documents: list[tuple[str, str, str]],
    outlier_threshold: Decimal = rules.DEFAULT_OUTLIER_THRESHOLD,
) -> CheckResult:
    """Runs all six checks for `period_id` and returns what should change.

    `expected_documents` and `prior_period_activities` are supplied by the
    caller (not inferred here) — the Checker never invents what "should"
    exist; it only compares to what you tell it was expected or happened
    last period.
    """
    sites_by_id = {s["id"]: s for s in sites}
    sites_by_region = {s["grid_subregion"]: s for s in sites}
    periods_by_id = {p["id"]: p for p in periods}
    activities_by_id = {a["id"]: a for a in activities}
    source_docs_by_id = {d["id"]: d for d in source_docs}
    factors_by_id = {f["id"]: f for f in factors}
    existing_keys = {g["dedupe_key"] for g in existing_gaps}

    period_activities = [a for a in activities if a["period_id"] == period_id]

    result = CheckResult()

    candidates: list[GapCandidate] = []

    candidates += rules.check_missing_documents(expected_documents, period_activities, sites_by_id)

    conflict_gaps, conflict_status = rules.check_conflicts(period_activities, sites_by_id)
    candidates += conflict_gaps
    _merge_status(result.status_updates, conflict_status)

    stale_gaps, stale_status = rules.check_stale_factor(
        [c for c in calculations if activities_by_id.get(c["activity_id"], {}).get("period_id") == period_id],
        activities_by_id, factors_by_id, periods_by_id, sites_by_id,
    )
    candidates += stale_gaps
    _merge_status(result.status_updates, stale_status)

    outlier_gaps, outlier_status = rules.check_outliers(
        period_activities, prior_period_activities, sites_by_id, outlier_threshold,
    )
    candidates += outlier_gaps
    _merge_status(result.status_updates, outlier_status)

    false_done_gaps, false_done_status = rules.check_false_done(
        period_activities, source_docs_by_id, sites_by_id,
    )
    candidates += false_done_gaps
    _merge_status(result.status_updates, false_done_status)

    rec_gaps, instrument_updates = rules.check_rec_quality(
        [i for i in instruments if i["period_id"] == period_id], sites_by_region, periods_by_id,
    )
    candidates += rec_gaps
    result.instrument_updates.update(instrument_updates)

    for candidate in candidates:
        if candidate.dedupe_key in existing_keys:
            continue  # idempotent: never re-create a gap we already raised
        gap_row = _to_gap_row(candidate)
        result.new_gaps.append(gap_row)
        if candidate.activity_ids:
            result.gap_activity_ids[gap_row["id"]] = candidate.activity_ids
        existing_keys.add(candidate.dedupe_key)

    for gap in result.new_gaps:
        result.events.append({
            "actor": "cr-checker",
            "action": "gap_opened",
            "ref": {"gap_id": gap["id"], "kind": gap["kind"], "site_id": gap["site_id"]},
        })
    for activity_id, new_status in result.status_updates.items():
        old_status = activities_by_id.get(activity_id, {}).get("status")
        if old_status != new_status:
            result.events.append({
                "actor": "cr-checker",
                "action": "status_changed",
                "ref": {"activity_id": activity_id, "before_status": old_status, "after_status": new_status},
            })

    return result


def promote_clean_activities(
    activities: list[dict],
    flagged_or_conflicting_ids: set[str],
) -> dict[str, str]:
    """Any UNVERIFIED activity that tripped none of this run's checks, and
    has a source document attached, is promoted to VERIFIED. An activity
    the checks just flagged/conflicted is excluded by the caller (pass the
    keys of status_updates in `flagged_or_conflicting_ids`)."""
    promotions: dict[str, str] = {}
    for a in activities:
        if a["status"] != "UNVERIFIED":
            continue
        if a["id"] in flagged_or_conflicting_ids:
            continue
        if not a.get("source_doc_id"):
            continue
        promotions[a["id"]] = "VERIFIED"
    return promotions
