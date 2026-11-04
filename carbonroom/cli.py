"""carbonroom CLI -- the commands from Section 8.1.6 of the brief:

  carbonroom seed-demo                 (placeholder data until Person 1's ingestion lands)
  carbonroom calc    --period YYYY-MM
  carbonroom check   --period YYYY-MM
  carbonroom resolve <gap_id> --answer "..." --by <handle>
  carbonroom report  --period YYYY-MM [--draft | --publish] [--out PATH]
  carbonroom approve --period YYYY-MM --by <handle> [--reject] [--note TEXT]
  carbonroom ask "<question>" --period YYYY-MM

Each command opens the SQLite ledger (carbonroom/db.py), does its one job,
and writes back only what that command is allowed to touch -- same
permissions as Section 8.1's agent-org table.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone
from decimal import Decimal

from . import db, llm
from .calc import allocate_rec_coverage, calculate_activity, index_factors
from .check import (
    CandidateActivity,
    NeedsClarificationError,
    UnrecognizedResolutionError,
    promote_clean_activities,
    resolve_gap,
    run_checks,
    translate_reply,
)
from .report import ApprovalRecord, PublishRefusedError, answer_question, build_report, publish_report, render_markdown


def _describe_activity(activity: dict | None) -> str:
    if activity is None:
        return "(unknown activity)"
    return f"{activity.get('quantity')} {activity.get('unit')} ({activity.get('category')}), source: {activity.get('source_doc_id')}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _region_by_site(sites: list[dict]) -> dict[str, str]:
    return {s["id"]: s["grid_subregion"] for s in sites}


def _prior_period_id(periods: list[dict], period_id: str) -> str | None:
    earlier = sorted(p["id"] for p in periods if p["id"] < period_id)
    return earlier[-1] if earlier else None


# ---- commands -------------------------------------------------------------

def cmd_seed_demo(args) -> int:
    """Loads the same fixture used in our dry run, so `calc`/`check`/
    `report` have something real to run against before Person 1's
    ingestion pipeline is wired up. Clearly a placeholder: once real
    activities/source_docs are flowing in, skip this command entirely."""
    from .seed_demo import SEED

    conn = db.connect(args.db)
    db.init_schema(conn)
    for table in ("sites", "periods", "source_docs", "emission_factors", "activities", "instruments", "calculations"):
        db.upsert_many(conn, table, SEED[table])
    print(f"Seeded demo data into {args.db or db.default_db_path()}.")
    return 0


def cmd_calc(args) -> int:
    conn = db.connect(args.db)
    period = db.get_period(conn, args.period)
    if period is None:
        print(f"No period {args.period!r}. Run `seed-demo` or create it first.")
        return 1
    if not period.get("factor_set_version"):
        print(f"Period {args.period!r} has no locked factor_set_version. Lock one before calculating.")
        return 1

    sites = db.get_sites(conn)
    region_by_site = _region_by_site(sites)
    activities = db.get_activities(conn, args.period)
    instruments = db.get_instruments(conn, args.period)
    factors = db.get_factors(conn, period["factor_set_version"])
    factor_index = index_factors(factors)

    already_calculated = {c["activity_id"] for c in db.get_calculations(conn)}
    to_calculate = []
    for activity in activities:
        if not args.force and activity["status"] == "VERIFIED" and activity["id"] in already_calculated:
            # Already settled under whatever factor it was last calculated
            # with. Recalculating it unconditionally every run would mean
            # a stale-factor row could never actually BE stale long enough
            # for `check` to catch it -- recomputation happens on first
            # pass, or after a human's `resolve` sends it back to
            # UNVERIFIED, not blindly every time. Use --force to override.
            continue
        to_calculate.append(activity)

    coverage = allocate_rec_coverage(to_calculate, instruments, region_by_site)
    n_calcs = 0
    for activity in to_calculate:
        region = region_by_site.get(activity["site_id"])
        if region is None:
            print(f"[skip] {activity['id']}: site {activity['site_id']!r} has no known grid_subregion")
            continue
        calcs, issues, _extras = calculate_activity(
            activity, factor_index, region=region, instruments=instruments,
            covered_kwh=coverage.get(activity["id"], Decimal("0")),
        )
        for calc in calcs:
            db.upsert(conn, "calculations", calc)
            n_calcs += 1
        for issue in issues:
            print(f"[calc issue] {activity['id']}: {issue.code} - {issue.detail}")
    skipped = len(activities) - len(to_calculate)
    print(f"Calculated {n_calcs} calculation row(s) for {len(to_calculate)} activities in {args.period}"
          + (f" ({skipped} already-settled VERIFIED activities skipped; use --force to redo them)." if skipped else "."))
    return 0


def cmd_check(args) -> int:
    conn = db.connect(args.db)
    sites = db.get_sites(conn)
    periods = db.get_periods(conn)
    all_activities = db.get_activities(conn)
    period_activities = [a for a in all_activities if a["period_id"] == args.period]
    prior_period_id = _prior_period_id(periods, args.period)
    prior_activities = [a for a in all_activities if a["period_id"] == prior_period_id] if prior_period_id else []

    expected_documents = sorted({(a["site_id"], args.period, a["category"]) for a in prior_activities})

    result = run_checks(
        period_id=args.period, sites=sites, periods=periods, activities=period_activities,
        prior_period_activities=prior_activities, source_docs=db.get_source_docs(conn),
        calculations=db.get_calculations(conn), factors=db.get_factors(conn),
        instruments=db.get_instruments(conn, args.period), existing_gaps=db.get_gaps(conn),
        expected_documents=expected_documents,
    )

    for gap in result.new_gaps:
        db.upsert(conn, "gaps", gap)
        ids = result.gap_activity_ids.get(gap["id"])
        if ids:
            db.set_gap_activity_ids(conn, gap["id"], ids)
        print(f"[{gap['kind']}] {gap['id']} owner={gap['owner_handle']} room={gap['room']}: {gap['detail']}")

    for activity_id, status in result.status_updates.items():
        db.update_activity_status(conn, activity_id, status)
    for instrument_id, quality in result.instrument_updates.items():
        db.update_instrument_quality(conn, instrument_id, quality)

    refreshed = db.get_activities(conn, args.period)
    promotions = promote_clean_activities(refreshed, set(result.status_updates.keys()))
    for activity_id, status in promotions.items():
        db.update_activity_status(conn, activity_id, status)
        print(f"[promoted] {activity_id} -> VERIFIED")

    for event in result.events:
        db.append_event(conn, at=_now_iso(), actor=event["actor"], action=event["action"], ref=event["ref"])

    print(f"Check complete: {len(result.new_gaps)} new gap(s), {len(promotions)} promotion(s).")
    return 0


# A pending LLM translation needs an explicit human confirm/cancel before
# it's applied. Deliberately disjoint from resolve.py's own vocabulary
# (e.g. "approve" is NOT a confirm word here) so a human who types an
# actual exact resolution command while a pending translation is sitting
# there gets that command honored directly, not swallowed as a confirmation.
_CONFIRM_WORDS = {"yes", "y", "confirm", "confirmed", "correct", "ok", "okay", "✅"}
_CANCEL_WORDS = {"no", "n", "cancel", "nevermind", "never mind"}


def _persist_resolution(conn, gap: dict, result, by: str) -> int:
    for activity_id, status in result.activity_status_updates.items():
        db.update_activity_status(conn, activity_id, status)
    db.update_fields(conn, "gaps", gap["id"], {
        "status": result.gap_status, "resolution": result.resolution_text,
        "resolved_by": by, "resolved_at": _now_iso(),
    })
    for event in result.events:
        db.append_event(conn, at=event["at"], actor=event["actor"], action=event["action"], ref=event["ref"])
    print(f"{gap['id']} -> {result.gap_status}: {result.resolution_text}")
    if result.activity_status_updates:
        print("Re-run `carbonroom check --period ...` (and `calc` if quantities changed) to re-verify.")
    return 0


def cmd_resolve(args) -> int:
    conn = db.connect(args.db)
    gap = db.get_gap(conn, args.gap_id)
    if gap is None:
        print(f"No such gap: {args.gap_id!r}")
        return 1
    candidate_ids = db.get_gap_activity_ids(conn, args.gap_id)
    answer = args.answer.strip()
    lower = answer.lower()

    pending = db.get_pending_resolution(conn, args.gap_id)
    if pending is not None:
        if lower in _CONFIRM_WORDS:
            db.clear_pending_resolution(conn, args.gap_id)
            try:
                result = resolve_gap(gap, pending["translated_text"], args.by, candidate_activity_ids=candidate_ids)
            except UnrecognizedResolutionError as e:
                # Ledger state moved under it (rare) -- refuse rather than
                # apply a translation that no longer cleanly validates.
                print(f"The pending translation no longer applies cleanly, refusing: {e}")
                return 1
            print(f"Confirmed by {args.by}. Applying: {pending['translated_text']}")
            return _persist_resolution(conn, gap, result, args.by)
        if lower in _CANCEL_WORDS:
            db.clear_pending_resolution(conn, args.gap_id)
            print(f"Cancelled -- {gap['id']} is still OPEN, nothing changed.")
            return 0
        # Anything else is a brand-new attempt, not a reply to the pending
        # translation -- supersede it rather than leaving a stale one behind.
        db.clear_pending_resolution(conn, args.gap_id)

    try:
        result = resolve_gap(gap, answer, args.by, candidate_activity_ids=candidate_ids)
    except UnrecognizedResolutionError as e:
        if not llm.is_configured():
            print(f"Could not apply that resolution: {e}")
            print("(No LLM configured to interpret free-form replies -- "
                  "set NVIDIA_API_KEY or ANTHROPIC_API_KEY to enable that, or use one of the exact formats.)")
            return 1

        activities_by_id = {a["id"]: a for a in db.get_activities(conn)}
        candidates = [
            CandidateActivity(aid, _describe_activity(activities_by_id.get(aid)))
            for aid in candidate_ids
        ]
        try:
            translated = translate_reply(gap, candidates, answer)
        except NeedsClarificationError as clarify_err:
            print(f"Could not confidently understand that reply: {clarify_err}")
            print("Please rephrase using one of: 'use <activity_id>', a number, "
                  "'exclude: <reason>', 'accept: <reason>', or 'approve'.")
            return 1

        # Do NOT apply yet. A model can pick the wrong action (e.g.
        # "exclude" when the human meant "accept") while still returning a
        # perfectly well-formed command -- resolve_gap's own validation
        # can't catch that, it's a comprehension error, not a syntax one.
        # A human must explicitly confirm before anything in the ledger changes.
        db.set_pending_resolution(
            conn, args.gap_id, translated_text=translated, proposed_by=args.by,
            original_reply=answer, proposed_at=_now_iso(),
        )
        print(f'I understood "{answer}" as: {translated}')
        print("Not applied yet -- reply 'yes' to confirm, 'no' to cancel, or rephrase "
              "using an exact format ('use <id>', 'exclude: ...', 'accept: ...', 'approve').")
        return 0

    db.clear_pending_resolution(conn, args.gap_id)  # a direct exact command supersedes any stale pending
    return _persist_resolution(conn, gap, result, args.by)


def cmd_report(args) -> int:
    conn = db.connect(args.db)
    report = build_report(
        company=args.company, period_id=args.period, sites=db.get_sites(conn),
        activities=db.get_activities(conn, args.period), calculations=db.get_calculations(conn),
        factors=db.get_factors(conn), gaps=db.get_gaps(conn, args.period),
        instruments=db.get_instruments(conn, args.period),
    )

    if args.publish:
        try:
            report = publish_report(report, db.get_approvals(conn, args.period))
        except PublishRefusedError as e:
            print(f"REFUSED to publish: {e}")
            return 1
        db.mark_period_closed(conn, args.period, report["approver"], _now_iso())
        db.append_event(conn, at=_now_iso(), actor=report["approver"], action="report_published",
                         ref={"period": args.period, "report_sha256": report["report_sha256"]})

    suffix = "published" if args.publish else "draft"
    out_path = pathlib.Path(args.out) if args.out else pathlib.Path(f"report-{args.period}-{suffix}.json")
    out_path.write_text(json.dumps(report, indent=2, default=str))
    out_path.with_suffix(".md").write_text(render_markdown(report))

    print(render_markdown(report))
    print(f"\nWrote {out_path} and {out_path.with_suffix('.md')}.")
    return 0


def cmd_approve(args) -> int:
    conn = db.connect(args.db)
    report = build_report(
        company=args.company, period_id=args.period, sites=db.get_sites(conn),
        activities=db.get_activities(conn, args.period), calculations=db.get_calculations(conn),
        factors=db.get_factors(conn), gaps=db.get_gaps(conn, args.period),
        instruments=db.get_instruments(conn, args.period),
    )
    decision = "REJECT" if args.reject else "APPROVE"
    record = ApprovalRecord(args.period, args.by, decision, report["report_sha256"], note=args.note)
    row = record.to_row(db.new_id("appr"))
    db.upsert(conn, "approvals", row)
    db.append_event(conn, at=row["at"], actor=args.by, action="approval_recorded",
                     ref={"period": args.period, "decision": decision, "report_sha256": report["report_sha256"]})
    print(f"{decision} recorded for {args.period} by {args.by}, bound to report_sha256={report['report_sha256'][:16]}...")
    if decision == "APPROVE":
        print("Run `carbonroom report --period ... --publish` to publish with this exact approval.")
    return 0


def cmd_ask(args) -> int:
    conn = db.connect(args.db)
    print(answer_question(
        args.question, period_id=args.period, sites=db.get_sites(conn),
        activities=db.get_activities(conn, args.period), calculations=db.get_calculations(conn),
        gaps=db.get_gaps(conn, args.period),
    ))
    return 0


# ---- argument parsing ------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carbonroom")
    parser.add_argument("--db", default=None, help="SQLite path (default: $CR_DB_PATH or ./carbonroom.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed-demo", help="load placeholder demo data (until Person 1's ingestion exists)").set_defaults(func=cmd_seed_demo)

    p = sub.add_parser("calc", help="run the deterministic Calculator for a period")
    p.add_argument("--period", required=True)
    p.add_argument("--force", action="store_true", help="recalculate even already-VERIFIED activities")
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("check", help="run the Checker/Watchdog for a period")
    p.add_argument("--period", required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("resolve", help="apply a human's reply to a gap")
    p.add_argument("gap_id")
    p.add_argument("--answer", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("report", help="build the close pack (draft or publish)")
    p.add_argument("--period", required=True)
    p.add_argument("--company", default="Brightwell Manufacturing")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("approve", help="record a human APPROVE/REJECT decision for a period's current draft")
    p.add_argument("--period", required=True)
    p.add_argument("--company", default="Brightwell Manufacturing")
    p.add_argument("--by", required=True)
    p.add_argument("--reject", action="store_true")
    p.add_argument("--note", default=None)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("ask", help="answer a question from VERIFIED rows only")
    p.add_argument("question")
    p.add_argument("--period", required=True)
    p.set_defaults(func=cmd_ask)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
