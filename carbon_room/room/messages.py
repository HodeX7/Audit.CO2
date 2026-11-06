"""Every message the room posts, as a pure function: values in, text out.

Templates format values that core returned. They never compute a figure, read config or call core.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from carbon_room.models import (
    AuditCheck,
    CloseSummary,
    DcLine,
    Finding,
    Gap,
    IngestReport,
    Option,
    Report,
    SourceTag,
)

UPLOAD_HINT: str = "Attach the file to your reply, or put it in data/inbox/ and reply `upload <file name>`."

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December")
_SEP = " · "


def _is_number(value: object) -> bool:
    return isinstance(value, (Decimal, int)) and not isinstance(value, bool)


def _tonnes(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.1"), ROUND_HALF_UP)
    return format(rounded, ",") + " tCO2e"


def t(kg: Decimal | int | None) -> str:
    if kg is None:
        return "n/a"
    if not _is_number(kg):
        raise TypeError("t() needs a Decimal")
    return _tonnes(Decimal(kg) / Decimal(1000))


def t_value(tco2e: Decimal | int | None) -> str:
    if tco2e is None:
        return "n/a"
    if not _is_number(tco2e):
        raise TypeError("t_value() needs a Decimal")
    return _tonnes(Decimal(tco2e))


def pct(p: Decimal | int | None) -> str:
    if p is None:
        return "n/a"
    if not _is_number(p):
        raise TypeError("pct() needs a Decimal")
    return format(Decimal(p).quantize(Decimal("1"), ROUND_HALF_UP), "f") + "%"


def month_label(month: str) -> str:
    parts = month.split("-") if isinstance(month, str) else []
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2 or not all(x.isdigit() for x in parts):
        raise ValueError(f"not a month: {month!r}")
    number = int(parts[1])
    if not 1 <= number <= 12:
        raise ValueError(f"not a month: {month!r}")
    return f"{_MONTHS[number - 1]} {parts[0]}"


def month_of(close_id: str) -> str:
    return close_id.rsplit("-v", 1)[0]


def _join(*blocks: str) -> str:
    return "\n\n".join(blocks)


def _render_key(option: Option) -> str:
    return "reject <reason>" if option.action == "reject" else option.key


def _figures(summary: CloseSummary) -> str:
    return (f"Verified: {t(summary.verified_kgco2e)}{_SEP}Excluded (not verified): "
            f"{t(summary.excluded_kgco2e)}{_SEP}Coverage: {pct(summary.coverage_pct)}")


def _sources(summary: CloseSummary) -> str:
    return f"Sources: {summary.sources_verified} of {summary.sources_expected} expected sources verified."


def close_plan(month_label: str, close_id: str, site_names: list[str], factor_set: str) -> str:
    return "\n".join([
        f"Starting the {month_label} close ({close_id}).",
        f"Sites: {', '.join(site_names)}. Factor set {factor_set} is locked.",
        "Plan: @collector gathers the sources, I calculate, @watchdog checks every row. "
        "Anything that fails a check becomes a thread with an owner.",
    ])


def handoff_collect(month_label: str, site_names: list[str]) -> str:
    return f"Collect {month_label} for {', '.join(site_names)}."


def handoff_check(month_label: str) -> str:
    return f"Check {month_label}: every rule, every claim."


def collector_statement(report: IngestReport) -> str:
    text = report.statement
    if report.failed_sources:
        text += f"\nCould not read {len(report.failed_sources)} file(s)."
    return text


def gap_root(gap: Gap, finding: Finding | None, owner_display: str, *, fallback_hint: bool = False) -> str:
    head = [f"**{gap.gap_id} · {gap.kind}** {gap.title}", f"Owner: {owner_display}"]
    if finding is not None and finding.evidence:
        head.append("Evidence:")
        head.extend(f"> {line}" for line in finding.evidence)
    blocks = ["\n".join(head)]
    if not gap.options:
        blocks.append(f"No reply needed. {owner_display} follows this up.")
        return _join(*blocks)
    option_lines = ["Reply in this thread with:"]
    option_lines.extend(f"- `{_render_key(o)}`: {o.label}" for o in gap.options)
    blocks.append("\n".join(option_lines))
    if any(o.action == "upload" for o in gap.options):
        blocks.append(UPLOAD_HINT)
    if fallback_hint:
        blocks.append(f"Or type `{gap.gap_id} {_render_key(gap.options[0])}` anywhere in the room.")
    return _join(*blocks)


def options_help(gap: Gap) -> str:
    keys = ", ".join(f"`{_render_key(o)}`" for o in gap.options)
    return f"I didn't catch that. Reply with one of: {keys}."


def already_resolved(gap: Gap) -> str:
    return f"{gap.gap_id} is already resolved."


def old_close_gap(gap: Gap) -> str:
    return (f"{gap.gap_id} belongs to an earlier close ({gap.close_id}). "
            "Reply in the thread from the current close.")


def checking() -> str:
    return "Checking…"


def outcome_resolved(gap: Gap) -> str:
    return f"Resolved. {gap.gap_id} is closed and the ledger is updated."


def outcome_open(gap: Gap, reason: str) -> str:
    end = "" if reason.endswith((".", "!", "?")) else "."
    return f"{gap.gap_id} is still open: {reason}{end}"


def summary_post(month_label: str, summary: CloseSummary, display: Callable[[str], str]) -> str:
    gaps = summary.open_gaps
    out = [f"I can't give a clean {month_label} total yet." if gaps else f"{month_label} is ready to draft.",
           _figures(summary), _sources(summary)]
    if gaps:
        items = _SEP.join(f"{g.gap_id} {display(g.owner)}" for g in gaps)
        out.append(f"Open gaps ({len(gaps)}): {items}")
    if summary.dc_line is not None:
        out.append(dc_line(summary.dc_line))
    if not gaps:
        out.append("Next: @reporter draft")
    return "\n".join(out)


def dc_line(dc: DcLine) -> str:
    return (f"Data centre: location-based {t(dc.location_kgco2e)}{_SEP}market-based {t(dc.market_kgco2e)} "
            f"({dc.rec_flag}){_SEP}AI line {dc.ai_line_status}: {dc.note}")


def total_moved(before: CloseSummary, after: CloseSummary) -> str:
    def n(x: CloseSummary) -> str:
        return t(x.verified_kgco2e).removesuffix(" tCO2e")

    return (f"Total moved {n(before)} → {n(after)} tCO2e, coverage "
            f"{pct(before.coverage_pct)} → {pct(after.coverage_pct)}.")


def _item_line(item: object) -> str:
    if isinstance(item, dict) and (item.get("gap_id") or item.get("title")):
        text = " ".join(str(item[k]) for k in ("gap_id", "title") if item.get(k))
        return f"- {text}"
    return f"- {str(item)}"


def _list_block(heading: str, items: list[str]) -> str:
    if not items:
        return f"{heading} none"
    return "\n".join([heading, *items])


def draft(report: Report, month_label: str) -> str:
    blocks = [
        "\n".join([
            f"**Draft v{report.version} for {month_label}**",
            f"Verified: {t_value(report.verified_total_tCO2e)}{_SEP}Excluded (not verified): "
            f"{t_value(report.unverified_excluded_tCO2e)}{_SEP}Coverage: {pct(report.coverage_pct)}"
            f"{_SEP}{report.source_coverage}",
        ]),
        _list_block("Open and excluded:", [_item_line(g) for g in report.gaps]),
        _list_block("Conflicts:", [_item_line(c) for c in report.conflicts]),
    ]
    if report.datacentre_line is not None:
        blocks.append(dc_line(report.datacentre_line))
    blocks.append(_list_block("Compliance:", [f"- {flag}" for flag in report.compliance_flags]))
    tags = report.s_tags
    if not tags:
        tags_line = "No verified lines yet, so there are no source tags."
    elif len(tags) == 1:
        tags_line = f"1 source tag. Ask @reporter trace {tags[0].tag} to see one."
    else:
        tags_line = f"{len(tags)} source tags. Ask @reporter trace {tags[0].tag} to see one."
    versions = ", ".join(report.factor_versions) or "none"
    blocks.append("\n".join([f"Factor versions: {versions}", tags_line,
                             "The Lead publishes with @carbon-room publish."]))
    return _join(*blocks)


def published(report: Report, approver_display: str, paths: list[str]) -> str:
    out = [f"Published v{report.version} by {approver_display}.",
           f"Verified: {t_value(report.verified_total_tCO2e)}{_SEP}Coverage: {pct(report.coverage_pct)}"
           f"{_SEP}{report.source_coverage}"]
    if report.gaps:
        out.append(f"Published with {len(report.gaps)} open gap(s); their rows are excluded.")
    out.append(f"Files: {', '.join(paths)}" if paths else "Files: none written")
    return "\n".join(out)


def trace_card(tag: SourceTag, link: str | None) -> str:
    approved = f"Approved by: {tag.approver or 'Tier 1 (automatic)'}"
    if link is not None:
        approved += f"{_SEP}{link}"
    return "\n".join([
        f"{tag.tag}{_SEP}{tag.activity}{_SEP}{tag.status}",
        f"File: {tag.file_name}, page {tag.page}",
        f'Excerpt: "{tag.excerpt}"',
        f"SHA-256: {tag.sha256[:12]}…",
        f"Factor: {tag.factor_id} ({tag.factor_version}, {tag.geography})",
        f"Recompute: {tag.recompute}",
        f"Result: {t(tag.kgco2e)}",
        approved,
    ])


def audit_result(check: AuditCheck) -> str:
    if check.ok:
        return f"Audit chain intact: {check.events} events."
    return f"Audit chain broken at event {check.first_bad_event_id} ({check.events} events checked)."


def resume_line(month_label: str, phase: str, gaps: list[Gap], display: Callable[[str], str],
                link: Callable[[str], str]) -> str:
    out = [f"Resuming the {month_label} close at {phase}."]
    if not gaps:
        out.append("No open gaps.")
    else:
        items = []
        for g in gaps:
            where = link(g.thread_root_message_id) if g.thread_root_message_id else "no thread yet"
            items.append(f"{g.gap_id} {display(g.owner)} ({where})")
        out.append("Open gaps: " + _SEP.join(items))
    return "\n".join(out)


def budget_warn(agent: str, warn_label: str) -> str:
    return f"@{agent} has used {warn_label} of its budget for this close."


def budget_stopped(agent: str) -> str:
    return f"@{agent} has hit its budget for this close and has stopped. The Lead can raise it in config."


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def board(month_label: str, summary: CloseSummary, display: Callable[[str], str],
          link: Callable[[str], str]) -> str:
    top = "\n".join([f"### Close Board · {month_label}", f"Phase: {summary.phase}",
                     _figures(summary), _sources(summary)])
    if not summary.open_gaps:
        return _join(top, "No open gaps.")
    rows = ["| Gap | Owner | Status | Thread |", "|---|---|---|---|"]
    for g in summary.open_gaps:
        thread = link(g.thread_root_message_id) if g.thread_root_message_id else "none"
        rows.append(f"| {_cell(g.gap_id + ' ' + g.title)} | {_cell(display(g.owner))} "
                    f"| {_cell(g.status)} | {_cell(thread)} |")
    return _join(top, "\n".join(rows))


def no_close() -> str:
    return "No close has started yet. Start one with `@carbon-room close <Month>`."


def gap_not_found(gap_id: str) -> str:
    return f"I can't find an open {gap_id} in this close."


def tag_not_found(tag: str) -> str:
    return f"I can't find {tag} in this close."


def no_reply_needed() -> str:
    return "No reply needed here."


_HELP_COMMANDS = "\n".join([
    "Here's what I understand:",
    "- `@carbon-room close <Month> [<YYYY>]`: start a month's close",
    "- `@carbon-room status`: show the current figures",
    "- `@carbon-room resume`: repost where the close stands",
    "- `@carbon-room publish`: publish the report (Lead only)",
    "- `@reporter draft`: draft the report",
    "- `@reporter trace <tag>`: show where one figure came from",
    "- `@reporter verify audit`: check the audit chain",
    "- `@<agent> <question>`: ask about the ledger",
])
_HELP_THREADS = ("In a gap thread, reply with one of the options it lists. "
                 "If threads don't work, type `G-<n> <option>` anywhere in the room.")


def help_text(reason: str | None = None) -> str:
    blocks = [_HELP_COMMANDS, _HELP_THREADS]
    if reason:
        blocks.insert(0, reason)
    return _join(*blocks)
