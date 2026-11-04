"""`carbonroom ask "<question>"` -- Honesty Rule 4 in code: if a question
touches only unverified/conflicting/stale/missing rows, the answer is
UNKNOWN, with the gap named and its owner, never a blended average and
never a silent estimate.

This is intentionally simple keyword matching, not NLP -- a hackathon
chat agent should feel free to do nicer intent parsing upstream and call
answer_question() with the site_id/category it already extracted; the
free-text path here is a convenience for the CLI and for quick testing.
"""

from __future__ import annotations

from decimal import Decimal

_CATEGORY_KEYWORDS = {
    "electricity": ["electricity", "power", "kwh"],
    "natural_gas": ["natural gas", "gas"],
    "diesel": ["diesel", "fuel"],
    "cloud_compute": ["cloud", "data centre", "data center", "datacentre", "datacenter", "ai"],
}

_SCOPE_BY_CATEGORY = {
    "natural_gas": "1", "diesel": "1", "electricity": "2_location", "cloud_compute": "dc_location",
}


def _find_site_id(question: str, sites: list[dict]) -> str | None:
    q = question.lower()
    for site in sites:
        if site["id"].lower() in q or site["name"].lower() in q:
            return site["id"]
    return None


def _find_category(question: str) -> str | None:
    q = question.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return category
    return None


def answer_question(
    question: str,
    *,
    period_id: str,
    sites: list[dict],
    activities: list[dict],
    calculations: list[dict],
    gaps: list[dict],
) -> str:
    site_id = _find_site_id(question, sites)
    category = _find_category(question)

    matched = [
        a for a in activities
        if a["period_id"] == period_id
        and (site_id is None or a["site_id"] == site_id)
        and (category is None or a["category"] == category)
    ]

    def _matching_gap() -> dict | None:
        return next(
            (g for g in gaps if g["period_id"] == period_id
             and (site_id is None or g.get("site_id") == site_id)),
            None,
        )

    if not matched:
        # No activity at all for this scope -- e.g. a missing bill never
        # even produced a row. This is exactly the case Honesty Rule 4
        # cares about most, so always check for a gap naming the owner.
        scope_desc = f"{category or 'any category'} at {site_id or 'any site'}"
        candidate_gap = _matching_gap()
        if candidate_gap:
            return (
                f"[Answer] UNKNOWN · {scope_desc} for {period_id} has no data "
                f"({candidate_gap['kind']}, {candidate_gap['id']}, owner: @{candidate_gap['owner_handle']})."
            )
        return f"[Answer] UNKNOWN · no data at all for {scope_desc} in {period_id}."

    verified = [a for a in matched if a["status"] == "VERIFIED"]
    excluded = [a for a in matched if a["status"] == "EXCLUDED"]
    pending = [a for a in matched if a["status"] not in ("VERIFIED", "EXCLUDED")]

    if not verified:
        # Touches only unverified/conflicting/flagged/missing rows -> UNKNOWN,
        # and name the gap + owner if one exists for this scope.
        candidate_gap = _matching_gap()
        if candidate_gap:
            return (
                f"[Answer] UNKNOWN · {site_id or 'this scope'} {category or ''} for {period_id} "
                f"is unresolved ({candidate_gap['kind']}, {candidate_gap['id']}, owner: "
                f"@{candidate_gap['owner_handle']})."
            ).replace("  ", " ")
        if pending:
            statuses = sorted({a["status"] for a in pending})
            return (
                f"[Answer] UNKNOWN · every matching row for {site_id or 'this scope'} {category or ''} "
                f"in {period_id} is still {'/'.join(statuses)}, not yet verified."
            ).replace("  ", " ")
        return (
            f"[Answer] UNKNOWN · every matching row for {site_id or 'this scope'} {category or ''} "
            f"in {period_id} was excluded by a human, nothing verified remains."
        ).replace("  ", " ")

    calcs_by_activity: dict[str, list[dict]] = {}
    for c in calculations:
        calcs_by_activity.setdefault(c["activity_id"], []).append(c)

    total_kg = Decimal("0")
    sources = 0
    for a in verified:
        scope = _SCOPE_BY_CATEGORY.get(a["category"])
        calc = next((c for c in calcs_by_activity.get(a["id"], []) if c["scope"] == scope), None)
        if calc is not None:
            total_kg += Decimal(str(calc["co2e_kg"]))
            sources += 1

    total_t = total_kg / Decimal("1000")
    scope_label = category or "all categories"
    site_label = site_id or "all sites"
    answer = f"[Answer] {period_id} {site_label} {scope_label}, verified: {total_t:.3f} tCO2e · sources: {sources}"
    notes = []
    if pending:
        notes.append(f"{len(pending)} row(s) still unverified, not included")
    if excluded:
        notes.append(f"{len(excluded)} row(s) excluded by a human")
    if notes:
        answer += f" ({'; '.join(notes)})"
    return answer
