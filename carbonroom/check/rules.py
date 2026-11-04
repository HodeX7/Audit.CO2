"""The five checks the Checker/Watchdog runs. Each is a pure function:
given the relevant slice of ledger state, it returns GapCandidate rows and
proposed activity-status changes. Nothing here writes to a database or
decides anything on its own — a gap only becomes real once the orchestrator
(watchdog.py) checks it isn't a duplicate of an existing gap.

Status rules the Checker must obey (contracts/schema.sql):
  - may set VERIFIED, FLAGGED, CONFLICTING
  - may NEVER set EXCLUDED or SUPERSEDED (human-only, via a resolution)
  - may NEVER silently fix the data itself
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Statuses an activity can be in and still be "live" (i.e. worth checking).
# EXCLUDED/SUPERSEDED/MISSING are already resolved/handled; leave them alone.
LIVE_STATUSES = {"UNVERIFIED", "VERIFIED", "FLAGGED", "CONFLICTING"}

DEFAULT_OUTLIER_THRESHOLD = Decimal("0.40")


def _fmt_qty(value) -> str:
    """Formats a quantity for a human-readable gap message, trimming a
    trailing '.0' SQLite's REAL columns otherwise introduce (e.g. a
    quantity stored as "500" comes back as the float 500.0). Exists only
    for message cosmetics -- every actual calculation always goes through
    Decimal(str(value)), never this."""
    d = Decimal(str(value))
    return f"{d:f}".rstrip("0").rstrip(".") if "." in f"{d:f}" else f"{d:f}"


@dataclass(frozen=True)
class GapCandidate:
    kind: str
    period_id: str
    site_id: str | None
    detail: str
    owner_handle: str
    room: str
    dedupe_key: str
    activity_ids: tuple[str, ...] = ()
    instrument_id: str | None = None


def _site_owner_room(sites_by_id: dict, site_id: str | None) -> tuple[str, str]:
    site = sites_by_id.get(site_id) if site_id else None
    if site is None:
        return "unassigned", "cr-close"
    return site["owner_handle"], site["room"]


def check_missing_documents(
    expected: list[tuple[str, str, str]],  # (site_id, period_id, category)
    activities: list[dict],
    sites_by_id: dict,
) -> list[GapCandidate]:
    """Compares an expected (site, period, category) list — built by the
    caller, e.g. from what a site reported last period — against what
    actually exists. Anything expected with zero live activities becomes
    a MISSING gap. This function never invents the expectation itself."""
    have = {
        (a["site_id"], a["period_id"], a["category"])
        for a in activities
        if a["status"] in LIVE_STATUSES
    }
    gaps = []
    for site_id, period_id, category in expected:
        if (site_id, period_id, category) in have:
            continue
        owner, room = _site_owner_room(sites_by_id, site_id)
        gaps.append(GapCandidate(
            kind="missing_doc",
            period_id=period_id,
            site_id=site_id,
            detail=f"No {category} document found for {site_id} in {period_id}.",
            owner_handle=owner,
            room=room,
            dedupe_key=f"missing_doc:{period_id}:{site_id}:{category}",
        ))
    return gaps


def check_conflicts(
    activities: list[dict],
    sites_by_id: dict,
) -> tuple[list[GapCandidate], dict[str, str]]:
    """Groups live activities that share an explicit delivery_id (e.g. two
    invoices for the same diesel delivery) and flags disagreeing quantities
    within that group as CONFLICTING. Activities with no delivery_id are
    NOT grouped by (site, period, category) alone: a site can legitimately
    have more than one document for the same category in the same month
    (sub-meters, partial invoices), and guessing that those disagree would
    manufacture a conflict that was never actually there."""
    groups: dict[tuple, list[dict]] = {}
    for a in activities:
        if a["status"] not in LIVE_STATUSES:
            continue
        delivery_id = (a.get("extra_json") or {}).get("delivery_id")
        if delivery_id is None:
            continue
        key = (a["site_id"], a["period_id"], a["category"], delivery_id)
        groups.setdefault(key, []).append(a)

    gaps: list[GapCandidate] = []
    status_updates: dict[str, str] = {}
    for (site_id, period_id, category, delivery_id), rows in groups.items():
        if len(rows) < 2:
            continue
        quantities = {Decimal(str(r["quantity"])) for r in rows}
        if len(quantities) < 2:
            continue  # same claim filed twice, not a real conflict
        ids = tuple(sorted(r["id"] for r in rows))
        owner, room = _site_owner_room(sites_by_id, site_id)
        qty_list = ", ".join(f"{r['id']}={_fmt_qty(r['quantity'])}{r['unit']}" for r in rows)
        gaps.append(GapCandidate(
            kind="conflict",
            period_id=period_id,
            site_id=site_id,
            detail=f"{len(rows)} {category} activities disagree for {site_id} {period_id}: {qty_list}",
            owner_handle=owner,
            room=room,
            dedupe_key=f"conflict:{period_id}:{site_id}:{category}:{delivery_id}:{':'.join(ids)}",
            activity_ids=ids,
        ))
        for activity_id in ids:
            status_updates[activity_id] = "CONFLICTING"
    return gaps, status_updates


def check_stale_factor(
    calculations: list[dict],
    activities_by_id: dict,
    factors_by_id: dict,
    periods_by_id: dict,
    sites_by_id: dict,
) -> tuple[list[GapCandidate], dict[str, str]]:
    """A calculation whose factor's set_version doesn't match the period's
    locked factor_set_version used an edition that is no longer current."""
    gaps: list[GapCandidate] = []
    status_updates: dict[str, str] = {}
    for calc in calculations:
        activity = activities_by_id.get(calc["activity_id"])
        if activity is None or activity["status"] not in LIVE_STATUSES:
            continue
        period = periods_by_id.get(activity["period_id"])
        factor = factors_by_id.get(calc["factor_id"])
        if period is None or factor is None or not period.get("factor_set_version"):
            continue
        if factor["set_version"] == period["factor_set_version"]:
            continue
        owner, room = _site_owner_room(sites_by_id, activity["site_id"])
        gaps.append(GapCandidate(
            kind="stale_factor",
            period_id=activity["period_id"],
            site_id=activity["site_id"],
            detail=(
                f"{activity['id']} was calculated with factor set "
                f"'{factor['set_version']}', but {activity['period_id']} is locked to "
                f"'{period['factor_set_version']}'."
            ),
            owner_handle=owner,
            room=room,
            dedupe_key=f"stale_factor:{calc['id']}",
            activity_ids=(activity["id"],),
        ))
        status_updates[activity["id"]] = "FLAGGED"
    return gaps, status_updates


def check_outliers(
    activities: list[dict],
    prior_period_activities: list[dict],
    sites_by_id: dict,
    threshold: Decimal = DEFAULT_OUTLIER_THRESHOLD,
) -> tuple[list[GapCandidate], dict[str, str]]:
    """Flags a (site, category) whose quantity moved more than `threshold`
    versus the same (site, category) last period. Needs matching units;
    mismatched units are skipped rather than guessed."""
    prior_by_key: dict[tuple, Decimal] = {}
    for a in prior_period_activities:
        if a["status"] not in LIVE_STATUSES:
            continue
        key = (a["site_id"], a["category"], a["unit"])
        prior_by_key[key] = prior_by_key.get(key, Decimal("0")) + Decimal(str(a["quantity"]))

    gaps: list[GapCandidate] = []
    status_updates: dict[str, str] = {}
    current_by_key: dict[tuple, list[dict]] = {}
    for a in activities:
        if a["status"] not in LIVE_STATUSES:
            continue
        key = (a["site_id"], a["category"], a["unit"])
        current_by_key.setdefault(key, []).append(a)

    for key, rows in current_by_key.items():
        site_id, category, unit = key
        prior_qty = prior_by_key.get(key)
        if prior_qty is None or prior_qty == 0:
            continue  # no baseline to compare against
        current_qty = sum(Decimal(str(r["quantity"])) for r in rows)
        try:
            change = (current_qty - prior_qty) / prior_qty
        except InvalidOperation:
            continue
        if abs(change) <= threshold:
            continue
        owner, room = _site_owner_room(sites_by_id, site_id)
        pct = (change * 100).quantize(Decimal("0.1"))
        ids = tuple(sorted(r["id"] for r in rows))
        gaps.append(GapCandidate(
            kind="outlier",
            period_id=rows[0]["period_id"],
            site_id=site_id,
            detail=f"{site_id} {category} is {pct}% vs last period ({_fmt_qty(prior_qty)}{unit} -> {_fmt_qty(current_qty)}{unit}).",
            owner_handle=owner,
            room=room,
            dedupe_key=f"outlier:{rows[0]['period_id']}:{site_id}:{category}",
            activity_ids=ids,
        ))
        for activity_id in ids:
            status_updates[activity_id] = "FLAGGED"
    return gaps, status_updates


def check_false_done(
    activities: list[dict],
    source_docs_by_id: dict,
    sites_by_id: dict,
) -> tuple[list[GapCandidate], dict[str, str]]:
    """Re-reads the source behind every VERIFIED activity. If that source
    document has since been superseded by a corrected one, the excerpt a
    human signed off on no longer reflects the true document — the claim
    was 'done', but done is a claim, not a fact, until this check passes.
    Reopens it to FLAGGED rather than trusting the old VERIFIED status."""
    gaps: list[GapCandidate] = []
    status_updates: dict[str, str] = {}
    for a in activities:
        if a["status"] != "VERIFIED":
            continue
        doc = source_docs_by_id.get(a.get("source_doc_id"))
        if doc is None:
            owner, room = _site_owner_room(sites_by_id, a["site_id"])
            gaps.append(GapCandidate(
                kind="excerpt_mismatch",
                period_id=a["period_id"],
                site_id=a["site_id"],
                detail=f"{a['id']} is VERIFIED but its source document {a.get('source_doc_id')!r} no longer exists.",
                owner_handle=owner,
                room=room,
                dedupe_key=f"excerpt_mismatch:{a['id']}:missing_doc",
                activity_ids=(a["id"],),
            ))
            status_updates[a["id"]] = "FLAGGED"
            continue
        if doc.get("superseded_by"):
            owner, room = _site_owner_room(sites_by_id, a["site_id"])
            gaps.append(GapCandidate(
                kind="excerpt_mismatch",
                period_id=a["period_id"],
                site_id=a["site_id"],
                detail=(
                    f"{a['id']} was marked VERIFIED against {doc['id']}, which has since "
                    f"been superseded by {doc['superseded_by']}. Reopening: done was a claim, not a fact."
                ),
                owner_handle=owner,
                room=room,
                dedupe_key=f"excerpt_mismatch:{a['id']}:{doc['superseded_by']}",
                activity_ids=(a["id"],),
            ))
            status_updates[a["id"]] = "FLAGGED"
    return gaps, status_updates


def check_rec_quality(
    instruments: list[dict],
    sites_by_region: dict,
    periods_by_id: dict,
) -> tuple[list[GapCandidate], dict[str, str]]:
    """Flags an instrument (REC/PPA) whose region or vintage doesn't match
    the period it's claimed against. Returns gaps plus instrument_id ->
    quality_flags updates (the Calculator already ignores anything not
    flagged 'ok', so this is what makes that exclusion visible to humans)."""
    gaps: list[GapCandidate] = []
    quality_updates: dict[str, str] = {}
    for inst in instruments:
        period = periods_by_id.get(inst["period_id"])
        period_year = inst["period_id"].split("-")[0] if period else None
        problems = []
        if inst["region"] not in sites_by_region:
            problems.append(f"region {inst['region']!r} does not match any known site")
        if period_year and inst["vintage"] != period_year:
            problems.append(f"vintage {inst['vintage']!r} does not match period year {period_year!r}")
        if not problems:
            quality_updates[inst["id"]] = "ok"
            continue
        quality_updates[inst["id"]] = "flagged"
        site = sites_by_region.get(inst["region"])
        owner = site["owner_handle"] if site else "unassigned"
        room = site["room"] if site else "cr-close"
        gaps.append(GapCandidate(
            kind="rec_quality",
            period_id=inst["period_id"],
            site_id=site["id"] if site else None,
            detail=f"Instrument {inst['id']}: " + "; ".join(problems),
            owner_handle=owner,
            room=room,
            dedupe_key=f"rec_quality:{inst['id']}",
            instrument_id=inst["id"],
        ))
    return gaps, quality_updates
