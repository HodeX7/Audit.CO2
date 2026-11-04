"""The Calculator: deterministic code only. No LLM arithmetic anywhere.

Input:  one `activities` row (dict, see contracts/schema.sql) + the factor
        index for the period's locked set + any `instruments` (RECs/PPAs)
        for that site/period.
Output: a list of `calculations` rows (dict, see contracts/schema.sql),
        plus a list of CalcIssue — things the Calculator refused to guess.
        An activity with an issue produces no calculation for that scope;
        it is the Checker's job (carbonroom/check) to turn that issue into
        a `gaps` row owned by a human. The Calculator never invents a
        missing input (e.g. a missing PUE) to make the arithmetic work.

Nothing here writes to the ledger or decides VERIFIED/UNVERIFIED status.
That is the Checker's and the human's job. The Calculator only computes
numbers from whatever activity it is handed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from . import units
from .factors import FactorNotFoundError, get_factor

CODE_VERSION = "calc-0.1.0"


@dataclass(frozen=True)
class CalcIssue:
    code: str       # e.g. "missing_factor", "missing_pue", "unsupported_unit"
    detail: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _calc_id(activity_id: str, scope: str) -> str:
    """Deterministic id: recomputing the same (activity, scope) always
    produces the same calculation id, so a re-run upserts instead of
    piling up duplicate rows."""
    digest = hashlib.sha256(f"{activity_id}:{scope}".encode()).hexdigest()[:16]
    return f"calc-{digest}"


def _make_calc(activity_id: str, factor_row: dict, scope: str, co2e_kg: Decimal) -> dict:
    return {
        "id": _calc_id(activity_id, scope),
        "activity_id": activity_id,
        "factor_id": factor_row["id"],
        "scope": scope,
        "co2e_kg": co2e_kg,
        "computed_at": _now_iso(),
        "code_version": CODE_VERSION,
    }


def allocate_rec_coverage(
    activities: list[dict],
    instruments: list[dict],
    region_by_site: dict[str, str],
) -> dict[str, Decimal]:
    """Allocates each valid instrument's MWh (as kWh) ONCE across every
    electricity/cloud_compute activity that shares its region and period,
    in deterministic activity-id order. Without this, a single REC would
    be counted as a full offset separately against every activity that
    happens to sit in the same grid region -- the same MWh used twice.

    Returns {activity_id: covered_kwh}, to be passed as `covered_kwh` into
    calculate_scope2_electricity / calculate_cloud for that activity.
    `region_by_site` must map each activity's site_id to its eGRID
    subregion (from the `sites` table) -- the Calculator never guesses it.

    IMPORTANT for callers: an activity_id absent from this dict got ZERO
    coverage -- pass `covered.get(activity_id, Decimal("0"))`, never
    `covered.get(activity_id)`. Passing bare `None` through to
    calculate_activity() tells it to fall back to its own naive per-activity
    REC lookup, which is exactly the double-counting bug this function
    exists to prevent.
    """
    pool: dict[tuple[str, str], Decimal] = {}
    for inst in instruments:
        quality = (inst.get("quality_flags") or "ok").strip().lower()
        if quality not in ("", "ok"):
            continue
        key = (inst["region"], inst["period_id"])
        pool[key] = pool.get(key, Decimal("0")) + Decimal(str(inst["mwh"])) * Decimal("1000")

    covered: dict[str, Decimal] = {}
    relevant = sorted(
        (a for a in activities if a["category"] in ("electricity", "cloud_compute")),
        key=lambda a: a["id"],
    )
    for a in relevant:
        region = region_by_site.get(a["site_id"])
        key = (region, a["period_id"])
        available = pool.get(key, Decimal("0"))
        if available <= 0:
            continue
        try:
            if a["category"] == "cloud_compute":
                extra = a.get("extra_json") or {}
                if extra.get("pue") is None:
                    continue  # same as the Calculator: no guessed PUE, no coverage either
                usage_kwh = units.to_kwh(Decimal(str(a["quantity"])), a["unit"]) * Decimal(str(extra["pue"]))
            else:
                usage_kwh = units.to_kwh(Decimal(str(a["quantity"])), a["unit"])
        except units.UnsupportedUnitError:
            continue
        taken = min(available, usage_kwh)
        if taken > 0:
            covered[a["id"]] = taken
            pool[key] = available - taken
    return covered


def _valid_instrument_kwh(instruments: list[dict], region: str, period_id: str) -> Decimal:
    """Sum of MWh->kWh from instruments that actually match this site's
    region and this period, and carry no quality flag. A REC from the
    wrong region/vintage, or one the Checker already flagged, offsets
    nothing here — it stays visible as a gap instead of quietly working."""
    total_kwh = Decimal("0")
    for inst in instruments:
        if inst.get("region") != region:
            continue
        if inst.get("period_id") != period_id:
            continue
        quality = (inst.get("quality_flags") or "ok").strip().lower()
        if quality not in ("", "ok"):
            continue
        total_kwh += Decimal(str(inst["mwh"])) * Decimal("1000")
    return total_kwh


def calculate_scope1(activity: dict, factor_index: dict) -> tuple[list[dict], list[CalcIssue]]:
    """natural_gas / diesel -> Scope 1."""
    category = activity["category"]
    issues: list[CalcIssue] = []

    try:
        if category == "natural_gas":
            qty_mmbtu = units.to_mmbtu(Decimal(str(activity["quantity"])), activity["unit"])
        elif category == "diesel":
            qty_mmbtu = units.to_gallons(Decimal(str(activity["quantity"])), activity["unit"])
        else:
            return [], [CalcIssue("wrong_category", f"calculate_scope1 got category={category!r}")]
    except units.UnsupportedUnitError as e:
        return [], [CalcIssue("unsupported_unit", str(e))]

    try:
        factor_row = get_factor(factor_index, category, "US", "1")
    except FactorNotFoundError as e:
        return [], [CalcIssue("missing_factor", str(e))]

    co2e_kg = qty_mmbtu * factor_row["factor"]
    return [_make_calc(activity["id"], factor_row, "1", co2e_kg)], issues


def calculate_scope2_electricity(
    activity: dict,
    factor_index: dict,
    region: str,
    instruments: list[dict] | None = None,
    covered_kwh: Decimal | None = None,
) -> tuple[list[dict], list[CalcIssue]]:
    """electricity -> Scope 2, location-based AND market-based, side by side.

    `covered_kwh`, when given, is this activity's pre-allocated share of
    the region's RECs (from allocate_rec_coverage) and takes priority over
    recomputing the naive per-activity lookup -- which would double-count
    a REC shared with another activity in the same region/period. Pass it
    whenever you are calculating more than one activity in the same period;
    leave it out only for a true single-activity calculation."""
    instruments = instruments or []
    issues: list[CalcIssue] = []
    calcs: list[dict] = []

    try:
        qty_kwh = units.to_kwh(Decimal(str(activity["quantity"])), activity["unit"])
    except units.UnsupportedUnitError as e:
        return [], [CalcIssue("unsupported_unit", str(e))]

    # Location-based: the grid's actual average intensity. Always computed.
    try:
        loc_factor = get_factor(factor_index, "electricity", region, "2_location")
        calcs.append(_make_calc(activity["id"], loc_factor, "2_location", qty_kwh * loc_factor["factor"]))
    except FactorNotFoundError as e:
        issues.append(CalcIssue("missing_factor", str(e)))

    # Market-based: valid instruments offset their matched kWh at zero;
    # the uncovered remainder uses the residual-mix factor.
    try:
        mkt_factor = get_factor(factor_index, "electricity", region, "2_market")
        if covered_kwh is None:
            covered_kwh = _valid_instrument_kwh(instruments, region, activity["period_id"])
        covered = min(covered_kwh, qty_kwh)
        remainder_kwh = qty_kwh - covered
        calcs.append(_make_calc(activity["id"], mkt_factor, "2_market", remainder_kwh * mkt_factor["factor"]))
    except FactorNotFoundError as e:
        issues.append(CalcIssue("missing_factor", str(e)))

    return calcs, issues


def calculate_cloud(
    activity: dict,
    factor_index: dict,
    region: str,
    instruments: list[dict] | None = None,
    covered_kwh: Decimal | None = None,
) -> tuple[list[dict], list[CalcIssue], dict]:
    """cloud_compute (the data-centre / AI line) -> Scope 3 Cat. 1 for the
    buyer. Reported as its own 'dc_location' / 'dc_market' pair, never
    blended into Scope 1+2.

    facility_kWh = IT_kWh x PUE   (what the calc is actually based on)
    water_L      = IT_kWh x WUE   (per Section 8.1 — based on IT kWh, not facility kWh)

    PUE/WUE come from activity['extra_json'] (set by the Consolidator from
    the cloud invoice). If PUE is missing, we do not assume PUE=1 — that
    would silently understate the true facility draw — we raise an issue
    instead and skip the co2e calc; WUE missing only blocks the water
    figure, not the emissions figure.
    """
    instruments = instruments or []
    issues: list[CalcIssue] = []
    calcs: list[dict] = []
    extras: dict = {}

    extra = activity.get("extra_json") or {}
    pue = extra.get("pue")
    wue = extra.get("wue")

    try:
        it_kwh = units.to_kwh(Decimal(str(activity["quantity"])), activity["unit"])
    except units.UnsupportedUnitError as e:
        return [], [CalcIssue("unsupported_unit", str(e))], {}

    if pue is None:
        issues.append(CalcIssue("missing_pue", f"activity {activity['id']} has no PUE; cannot derive facility kWh"))
    else:
        facility_kwh = it_kwh * Decimal(str(pue))
        extras["facility_kwh"] = facility_kwh

        try:
            loc_factor = get_factor(factor_index, "electricity", region, "2_location")
            calcs.append(_make_calc(activity["id"], loc_factor, "dc_location", facility_kwh * loc_factor["factor"]))
        except FactorNotFoundError as e:
            issues.append(CalcIssue("missing_factor", str(e)))

        try:
            mkt_factor = get_factor(factor_index, "electricity", region, "2_market")
            if covered_kwh is None:
                covered_kwh = _valid_instrument_kwh(instruments, region, activity["period_id"])
            covered = min(covered_kwh, facility_kwh)
            remainder_kwh = facility_kwh - covered
            calcs.append(_make_calc(activity["id"], mkt_factor, "dc_market", remainder_kwh * mkt_factor["factor"]))
        except FactorNotFoundError as e:
            issues.append(CalcIssue("missing_factor", str(e)))

    if wue is None:
        issues.append(CalcIssue("missing_wue", f"activity {activity['id']} has no WUE; water figure unavailable"))
    else:
        extras["water_l"] = it_kwh * Decimal(str(wue))

    return calcs, issues, extras


def calculate_activity(
    activity: dict,
    factor_index: dict,
    region: str,
    instruments: list[dict] | None = None,
    covered_kwh: Decimal | None = None,
) -> tuple[list[dict], list[CalcIssue], dict]:
    """Dispatches by activity['category']. `region` is the site's
    (or cloud workload's) eGRID subregion — passed in rather than hardcoded,
    since it comes from `sites`/the activity, never from this module.

    When calculating more than one activity for the same period, call
    allocate_rec_coverage() first and pass each activity's share in as
    `covered_kwh` — otherwise a REC shared by several activities in the
    same region gets counted as a full offset against each of them."""
    category = activity["category"]
    if category in ("natural_gas", "diesel"):
        calcs, issues = calculate_scope1(activity, factor_index)
        return calcs, issues, {}
    if category == "electricity":
        calcs, issues = calculate_scope2_electricity(activity, factor_index, region, instruments, covered_kwh)
        return calcs, issues, {}
    if category == "cloud_compute":
        return calculate_cloud(activity, factor_index, region, instruments, covered_kwh)
    return [], [CalcIssue("unsupported_category", f"no calculator for category={category!r}")], {}
