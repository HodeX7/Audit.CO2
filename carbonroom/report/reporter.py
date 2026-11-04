"""The Reporter: builds the close pack from VERIFIED ledger rows only, and
refuses to publish without a real, matching human approval.

This is Honesty Rule 1 in code: "No one writes directly to the published
total. Only the human-approved Reporter output does." build_report() never
writes anything; publish_report() is the one function that is allowed to
mark a report PUBLISHED, and it hard-refuses without a matching approval.

Output matches contracts/report.schema.json exactly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

CODE_VERSION = "report-0.1.0"

LIVE_UNVERIFIED_STATUSES = {"UNVERIFIED", "FLAGGED", "CONFLICTING"}
_PRIMARY_SCOPE_BY_CATEGORY = {
    "natural_gas": "1",
    "diesel": "1",
    "electricity": "2_location",
    "cloud_compute": "dc_location",
}


class PublishRefusedError(Exception):
    """Raised when publish_report() is asked to publish without a valid,
    matching human approval. This is the hard gate; never catch this to
    "work around" it — fix the missing approval instead."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _kg_to_t(kg: Decimal) -> Decimal:
    return (kg / Decimal("1000")).quantize(Decimal("0.001"))


def _to_jsonable(value):
    """Decimal -> float only at the JSON boundary; everything upstream
    stays Decimal so the math itself is never float-imprecise."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _canonical_json(report: dict) -> str:
    """Deterministic serialization used to hash the report. Excludes the
    fields that are set only by/after publishing (status, approver,
    report_sha256), AND `generated_at` -- that field is just a build
    timestamp, not a number anyone is approving. Without excluding it,
    rebuilding the identical draft a second later (e.g. once by `approve`,
    once by `report --publish`) would hash differently purely from the
    clock moving, and a real, still-valid approval would wrongly stop
    matching. The hash must bind to the NUMBERS, not to when they were
    last computed."""
    stable = {k: v for k, v in report.items() if k not in ("status", "approver", "report_sha256", "generated_at")}
    return json.dumps(_to_jsonable(stable), sort_keys=True, separators=(",", ":"))


def _hash_report(report: dict) -> str:
    return hashlib.sha256(_canonical_json(report).encode()).hexdigest()


def _cloud_extras(activity: dict) -> dict:
    """Recomputes facility_kwh / water_l for display, from the same
    activity fields the Calculator used (IT kWh, PUE, WUE). Deterministic
    and cheap, so the Reporter doesn't need a second place these are
    stored — it is not a new source of truth, the activity row still is."""
    extra = activity.get("extra_json") or {}
    it_kwh = Decimal(str(activity["quantity"]))
    out = {"it_kwh": it_kwh}
    if extra.get("pue") is not None:
        out["pue"] = Decimal(str(extra["pue"]))
        out["facility_kwh"] = it_kwh * out["pue"]
    if extra.get("wue") is not None:
        out["wue"] = Decimal(str(extra["wue"]))
        out["water_l"] = it_kwh * out["wue"]
    return out


def build_report(
    *,
    company: str,
    period_id: str,
    sites: list[dict],
    activities: list[dict],
    calculations: list[dict],
    factors: list[dict],
    gaps: list[dict],
    instruments: list[dict] | None = None,
    prior_period_totals: dict | None = None,  # {"scope1": Decimal, "scope2_location": Decimal}, in tCO2e
) -> dict:
    """Builds a DRAFT report for one period. Reads raw ledger rows only —
    never a Collector/Consolidator "summary" — per Section 8.1 Rule 5."""
    instruments = instruments or []
    sites_by_id = {s["id"]: s for s in sites}
    factors_by_id = {f["id"]: f for f in factors}
    period_activities = [a for a in activities if a["period_id"] == period_id]
    calcs_by_activity: dict[str, list[dict]] = {}
    for c in calculations:
        calcs_by_activity.setdefault(c["activity_id"], []).append(c)

    verified = [a for a in period_activities if a["status"] == "VERIFIED"]
    unverified = [a for a in period_activities if a["status"] in LIVE_UNVERIFIED_STATUSES]

    totals_kg = {"scope1": Decimal("0"), "scope2_location": Decimal("0"), "scope2_market": Decimal("0")}
    by_site_kg: dict[str, dict] = {}
    verified_items = []
    evidence_index = []
    used_factor_ids: set[str] = set()

    dc_it_kwh = Decimal("0")
    dc_facility_kwh = Decimal("0")
    dc_water_l = Decimal("0")
    dc_pue_values: list[Decimal] = []
    dc_wue_values: list[Decimal] = []
    dc_loc_kg = Decimal("0")
    dc_mkt_kg = Decimal("0")

    for a in verified:
        site_bucket = by_site_kg.setdefault(a["site_id"], {"scope1": Decimal("0"), "scope2_location": Decimal("0"), "scope2_market": Decimal("0")})
        activity_calcs = calcs_by_activity.get(a["id"], [])
        for calc in activity_calcs:
            used_factor_ids.add(calc["factor_id"])
            if calc["scope"] == "1":
                totals_kg["scope1"] += calc["co2e_kg"]
                site_bucket["scope1"] += calc["co2e_kg"]
            elif calc["scope"] == "2_location":
                totals_kg["scope2_location"] += calc["co2e_kg"]
                site_bucket["scope2_location"] += calc["co2e_kg"]
            elif calc["scope"] == "2_market":
                totals_kg["scope2_market"] += calc["co2e_kg"]
                site_bucket["scope2_market"] += calc["co2e_kg"]
            elif calc["scope"] == "dc_location":
                dc_loc_kg += calc["co2e_kg"]
            elif calc["scope"] == "dc_market":
                dc_mkt_kg += calc["co2e_kg"]

        if a["category"] == "cloud_compute":
            extras = _cloud_extras(a)
            dc_it_kwh += extras["it_kwh"]
            if "facility_kwh" in extras:
                dc_facility_kwh += extras["facility_kwh"]
                dc_pue_values.append(extras["pue"])
            if "water_l" in extras:
                dc_water_l += extras["water_l"]
                dc_wue_values.append(extras["wue"])

        primary_scope = _PRIMARY_SCOPE_BY_CATEGORY.get(a["category"])
        primary_calc = next((c for c in activity_calcs if c["scope"] == primary_scope), None)
        if primary_calc is not None:
            verified_items.append({
                "activity_id": a["id"], "category": a["category"],
                "quantity": Decimal(str(a["quantity"])), "unit": a["unit"],
                "co2e_kg": primary_calc["co2e_kg"],
            })

        evidence_index.append({
            "activity_id": a["id"], "source_doc": a.get("source_doc_id"),
            "excerpt": a.get("excerpt"), "locator": a.get("excerpt_locator"),
            "sha256": a.get("excerpt_sha256"),
        })

    unverified_items = [{"activity_id": a["id"], "reason": a["status"]} for a in unverified]
    unverified_excluded_kg = Decimal("0")
    for a in unverified:
        for calc in calcs_by_activity.get(a["id"], []):
            if calc["scope"] in ("1", "2_location", "dc_location"):
                unverified_excluded_kg += calc["co2e_kg"]

    verified_total_t = _kg_to_t(totals_kg["scope1"] + totals_kg["scope2_location"] + dc_loc_kg)
    unverified_excluded_t = _kg_to_t(unverified_excluded_kg)
    denom = verified_total_t + unverified_excluded_t
    coverage_pct = float((verified_total_t / denom * 100).quantize(Decimal("0.1"))) if denom > 0 else None

    rec_quality = "ok"
    for inst in instruments:
        if inst["period_id"] == period_id and (inst.get("quality_flags") or "ok").lower() not in ("ok", ""):
            rec_quality = "flagged"
            break

    factor_set_versions = sorted({factors_by_id[fid]["set_version"] for fid in used_factor_ids if fid in factors_by_id})
    factor_sources = sorted({
        (factors_by_id[fid]["source_name"], factors_by_id[fid]["source_edition"])
        for fid in used_factor_ids if fid in factors_by_id
    })

    mom_change_pct = None
    if prior_period_totals:
        mom_change_pct = {}
        for key in ("scope1", "scope2_location"):
            prior = prior_period_totals.get(key)
            current_t = _kg_to_t(totals_kg[key])
            if prior and prior != 0:
                mom_change_pct[key] = float(((current_t - prior) / prior * 100).quantize(Decimal("0.1")))
            else:
                mom_change_pct[key] = None

    period_gaps = [g for g in gaps if g["period_id"] == period_id]

    report = {
        "type": "cr.report.v1",
        "company": company,
        "period": period_id,
        "status": "DRAFT",
        "factor_set": {
            "version": factor_set_versions[0] if len(factor_set_versions) == 1 else factor_set_versions,
            "sources": [{"name": n, "edition": e} for n, e in factor_sources],
        },
        "totals_t_co2e": {k: _kg_to_t(v) for k, v in totals_kg.items()},
        "data_centre": {
            "scope": "3 (Cat 1, purchased cloud services)",
            "it_kwh": dc_it_kwh,
            "pue": (sum(dc_pue_values) / len(dc_pue_values)) if dc_pue_values else None,
            "facility_kwh": dc_facility_kwh,
            "wue_l_per_kwh": (sum(dc_wue_values) / len(dc_wue_values)) if dc_wue_values else None,
            "water_l": dc_water_l,
            "co2e_location_t": _kg_to_t(dc_loc_kg),
            "co2e_market_t": _kg_to_t(dc_mkt_kg),
            "rec_quality": rec_quality,
        },
        "by_site": [
            {"site": sites_by_id.get(site_id, {}).get("name", site_id), **{k: _kg_to_t(v) for k, v in bucket.items()}}
            for site_id, bucket in by_site_kg.items()
        ],
        "mom_change_pct": mom_change_pct,
        "coverage_pct": coverage_pct,
        "unverified_excluded_t_co2e": unverified_excluded_t,
        "verified_items": verified_items,
        "unverified_items": unverified_items,
        "gaps": [
            {"gap_id": g["id"], "kind": g["kind"], "status": g["status"], "owner": g["owner_handle"], "resolution": g.get("resolution")}
            for g in period_gaps
        ],
        "evidence_index": evidence_index,
        "approver": None,
        "generated_at": _now_iso(),
    }
    report["report_sha256"] = _hash_report(report)
    return report


def render_markdown(report: dict) -> str:
    t = report["totals_t_co2e"]
    lines = [
        f"# {report['company']} — Emissions Close, {report['period']}",
        "",
        f"**Status:** {report['status']}" + (f" (approved by {report['approver']})" if report.get("approver") else ""),
        f"**Factor set:** {report['factor_set']['version']}",
        "",
        "## Closing slide",
        f"- {report['period']} total (verified only): **{t['scope1'] + t['scope2_location'] + report['data_centre']['co2e_location_t']} tCO2e**",
        f"- Unverified, excluded: **{report['unverified_excluded_t_co2e']} tCO2e**",
        f"- Coverage: **{report['coverage_pct']}% verified**" if report["coverage_pct"] is not None else "- Coverage: n/a (no verified or unverified data yet)",
        f"- Open gaps: {sum(1 for g in report['gaps'] if g['status'] == 'OPEN')}",
        "",
        "## Totals (verified only)",
        f"- Scope 1: {t['scope1']} tCO2e",
        f"- Scope 2, location-based: {t['scope2_location']} tCO2e",
        f"- Scope 2, market-based: {t['scope2_market']} tCO2e",
        "",
        "## Cloud / data-centre (Scope 3, Category 1 — reported separately, never blended into Scope 1+2)",
        f"- IT energy: {report['data_centre']['it_kwh']} kWh",
        f"- Facility energy (IT x PUE): {report['data_centre']['facility_kwh']} kWh",
        f"- Water (IT kWh x WUE): {report['data_centre']['water_l']} L",
        f"- Location-based: {report['data_centre']['co2e_location_t']} tCO2e",
        f"- Market-based: {report['data_centre']['co2e_market_t']} tCO2e",
        f"- REC/PPA quality: {report['data_centre']['rec_quality']}",
        "",
        "## Gaps",
    ]
    if report["gaps"]:
        for g in report["gaps"]:
            lines.append(f"- [{g['kind']}] {g['gap_id']} — owner: {g['owner']} — status: {g['status']}")
    else:
        lines.append("- none open")
    lines += ["", "## Unverified, excluded from the total"]
    if report["unverified_items"]:
        for item in report["unverified_items"]:
            lines.append(f"- {item['activity_id']} — {item['reason']}")
    else:
        lines.append("- none")
    lines += ["", f"_Generated {report['generated_at']} · report sha256 {report['report_sha256']}_"]
    return "\n".join(lines)


@dataclass
class ApprovalRecord:
    period_id: str
    approver_handle: str
    decision: str  # 'APPROVE' | 'REJECT'
    report_sha256: str
    note: str | None = None
    at: str | None = None

    def to_row(self, approval_id: str) -> dict:
        return {
            "id": approval_id, "period_id": self.period_id, "approver_handle": self.approver_handle,
            "decision": self.decision, "note": self.note, "report_sha256": self.report_sha256,
            "at": self.at or _now_iso(),
        }


def publish_report(draft_report: dict, approvals: list[dict]) -> dict:
    """The hard gate (Honesty Rule 1). Publishes ONLY if `approvals`
    contains an APPROVE decision whose report_sha256 matches this exact
    draft. A stale approval (from before the numbers changed) does not
    count — the hash binds the approval to these exact numbers."""
    if draft_report["status"] != "DRAFT":
        raise PublishRefusedError(f"report is already {draft_report['status']}, not DRAFT")

    matching = [
        a for a in approvals
        if a["period_id"] == draft_report["period"]
        and a["decision"] == "APPROVE"
        and a["report_sha256"] == draft_report["report_sha256"]
    ]
    if not matching:
        raise PublishRefusedError(
            f"no matching APPROVE for period {draft_report['period']!r} with "
            f"report_sha256={draft_report['report_sha256']!r}. Unapproved items stay "
            f"UNVERIFIED and excluded; nothing publishes on a timeout or on silence."
        )

    approval = matching[-1]  # most recent matching approval wins
    published = dict(draft_report)
    published["status"] = "PUBLISHED"
    published["approver"] = approval["approver_handle"]
    return published
