"""Message templates (SPEC-05 section 6): exact snapshots."""

from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from fakes.fake_core import FakeCore

from carbon_room.models import Actor, AuditCheck, Gap, IngestReport, SourceTag
from carbon_room.room.messages import (
    UPLOAD_HINT,
    already_resolved,
    audit_result,
    board,
    budget_stopped,
    budget_warn,
    checking,
    close_plan,
    collector_statement,
    dc_line,
    draft,
    gap_not_found,
    gap_root,
    handoff_check,
    handoff_collect,
    help_text,
    month_label,
    month_of,
    no_close,
    no_reply_needed,
    old_close_gap,
    options_help,
    outcome_open,
    outcome_resolved,
    pct,
    published,
    resume_line,
    summary_post,
    t,
    t_value,
    tag_not_found,
    total_moved,
    trace_card,
)

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
COLLECTOR = Actor("agent", "collector", "Collector")
G1_PARAMS = {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}
NAMES = ["HQ", "Warehouse-2", "Data Centre EU-West"]
D = lambda pid: f"@{pid}"  # noqa: E731
L = lambda mid: f"message {mid}"  # noqa: E731
MODULE = Path(__file__).resolve().parents[2] / "carbon_room" / "room" / "messages.py"

TAG = SourceTag("S-001", "hq_electricity_2026-10.pdf", 1, "Total consumption: 48300 kWh",
                "4c1d8e2a9b70" + "0" * 52, "electricity_kwh", Decimal("48300"), "kWh", "EGRID-2024-CAMX",
                "2024", "CAMX", "48300 kWh × 0.2 kgCO2e/kWh = 9660 kgCO2e", Decimal("9660"), "VERIFIED",
                "lead", "h-5")

E_DC = ("Data centre: location-based 4.3 tCO2e · market-based 0.0 tCO2e (Market-based 0 relies on "
        "certificates; certificate quality not verified) · AI line UNVERIFIED: "
        "No per-model AI breakdown on the invoice.")


def lines(*items):
    return "\n".join(items)


def scenario():
    fc = FakeCore()
    cid = fc.start_close("2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "h-1")
    fc.ingest(cid, COLLECTOR)
    fc.calculate(cid)
    findings = fc.check(cid)
    gaps = fc.resume_state(cid)[1]
    return fc, cid, findings, gaps


def g1(fc):
    fc.resolve("G-1", "upload", PRIYA, "h-2", {"path": "data/inbox/x.pdf", **G1_PARAMS})


def resolve_all(fc):
    g1(fc)
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    fc.resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})
    fc.resolve("G-4", "approve", LEAD, "h-5", {})


def with_roots(fc, cid):
    for n, mid in zip(range(1, 5), ("m-3", "m-4", "m-5", "m-6")):
        fc.record_gap_thread(cid, f"G-{n}", mid)
    return fc.resume_state(cid)[1]


E_PLAN = lines(
    "Starting the October 2026 close (2026-10-v1).",
    "Sites: HQ, Warehouse-2, Data Centre EU-West. Factor set FS-2026-10 is locked.",
    "Plan: @collector gathers the sources, I calculate, @watchdog checks every row. "
    "Anything that fails a check becomes a thread with an owner.",
)
E_G1 = lines(
    "**G-1 · PERIOD** Warehouse-2 October bill is a September bill",
    "Owner: @priya",
    "Evidence:",
    "> File name: warehouse2_electricity_2026-10.pdf",
    "> Billing period: 1–30 Sep 2026",
    "",
    "Reply in this thread with:",
    "- `upload`: Upload the October bill",
    "",
    "Attach the file to your reply, or put it in data/inbox/ and reply `upload <file name>`.",
)
E_G2 = lines(
    "**G-2 · CONFLICTING** HQ October diesel has two invoices 400 L apart",
    "Owner: @lead",
    "Evidence:",
    "> Invoice 4471: Diesel delivered: 2000 L",
    "> Invoice 4471-rev: Diesel delivered: 2400 L",
    "",
    "Reply in this thread with:",
    "- `pick A`: Invoice 4471 — 2,000 L",
    "- `pick B`: Invoice 4471-rev — 2,400 L",
)
E_G3 = lines(
    "**G-3 · STALE** Data centre invoice uses last year's Ember factor",
    "Owner: @lead",
    "Evidence:",
    "> vendor_factor_ref: Ember 2024 IE",
    "> Locked factor set FS-2026-10 uses Ember 2025",
    "",
    "Reply in this thread with:",
    "- `approve`: Use the locked Ember 2025 IE factor",
    "- `reject <reason>`: Exclude the cloud line",
)
E_G4_NOEV = lines(
    "**G-4 · VARIANCE** HQ October electricity is 38% above September",
    "Owner: @lead",
    "",
    "Reply in this thread with:",
    "- `approve`: Accept +38% against September",
    "- `reject <reason>`: Exclude HQ electricity",
)
E_G5 = lines(
    "**G-5 · DATACENTRE** Data centre invoice has no per-model AI breakdown",
    "Owner: @lead",
    "Evidence:",
    "> ai_breakdown: none on the invoice",
    "",
    "No reply needed. @lead follows this up.",
)
E_SUM_OPEN = lines(
    "I can't give a clean October 2026 total yet.",
    "Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0%",
    "Sources: 0 of 4 expected sources verified.",
    "Open gaps (4): G-1 @priya · G-2 @lead · G-3 @lead · G-4 @lead",
    E_DC,
)
E_SUM_G1 = lines(
    "I can't give a clean October 2026 total yet.",
    "Verified: 3.6 tCO2e · Excluded (not verified): 25.7 tCO2e · Coverage: 12%",
    "Sources: 1 of 4 expected sources verified.",
    "Open gaps (3): G-2 @lead · G-3 @lead · G-4 @lead",
    E_DC,
)
E_SUM_READY = lines(
    "October 2026 is ready to draft.",
    "Verified: 22.9 tCO2e · Excluded (not verified): 0.0 tCO2e · Coverage: 100%",
    "Sources: 4 of 4 expected sources verified.",
    E_DC,
    "Next: @reporter draft",
)
E_DRAFT_OPEN = lines(
    "**Draft v1 for October 2026**",
    "Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0% · "
    "0 of 4 expected sources verified",
    "",
    "Open and excluded:",
    "- G-1 Warehouse-2 October bill is a September bill",
    "- G-2 HQ October diesel has two invoices 400 L apart",
    "- G-3 Data centre invoice uses last year's Ember factor",
    "- G-4 HQ October electricity is 38% above September",
    "",
    "Conflicts:",
    "- G-2 HQ October diesel has two invoices 400 L apart",
    "",
    E_DC,
    "",
    "Compliance:",
    "- Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero",
    "",
    "Factor versions: DEFRA 2026, EGRID 2024, EMBER 2025",
    "No verified lines yet, so there are no source tags.",
    "The Lead publishes with @carbon-room publish.",
)
E_DRAFT_DONE = lines(
    "**Draft v1 for October 2026**",
    "Verified: 22.9 tCO2e · Excluded (not verified): 0.0 tCO2e · Coverage: 100% · "
    "4 of 4 expected sources verified",
    "",
    "Open and excluded: none",
    "",
    "Conflicts: none",
    "",
    E_DC,
    "",
    "Compliance:",
    "- Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero",
    "",
    "Factor versions: DEFRA 2026, EGRID 2024, EMBER 2025",
    "4 source tags. Ask @reporter trace S-001 to see one.",
    "The Lead publishes with @carbon-room publish.",
)
E_PUB = lines(
    "Published v1 by @lead.",
    "Verified: 22.9 tCO2e · Coverage: 100% · 4 of 4 expected sources verified",
    "Files: out/2026-10/v1/coverage.html, out/2026-10/v1/report.md",
)
E_TRACE = lines(
    "S-001 · electricity_kwh · VERIFIED",
    "File: hq_electricity_2026-10.pdf, page 1",
    'Excerpt: "Total consumption: 48300 kWh"',
    "SHA-256: 4c1d8e2a9b70…",
    "Factor: EGRID-2024-CAMX (2024, CAMX)",
    "Recompute: 48300 kWh × 0.2 kgCO2e/kWh = 9660 kgCO2e",
    "Result: 9.7 tCO2e",
    "Approved by: lead · message h-5",
)
E_RESUME = lines(
    "Resuming the October 2026 close at AWAITING_HUMANS.",
    "Open gaps: G-1 @priya (message m-3) · G-2 @lead (message m-4) · G-3 @lead (message m-5) · "
    "G-4 @lead (message m-6)",
)
E_BOARD = lines(
    "### Close Board · October 2026",
    "Phase: AWAITING_HUMANS",
    "Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0%",
    "Sources: 0 of 4 expected sources verified.",
    "",
    "| Gap | Owner | Status | Thread |",
    "|---|---|---|---|",
    "| G-1 Warehouse-2 October bill is a September bill | @priya | OPEN | message m-3 |",
    "| G-2 HQ October diesel has two invoices 400 L apart | @lead | OPEN | message m-4 |",
    "| G-3 Data centre invoice uses last year's Ember factor | @lead | OPEN | message m-5 |",
    "| G-4 HQ October electricity is 38% above September | @lead | OPEN | message m-6 |",
)
E_PIPE = "| G-1 a \\| b | @priya | OPEN | none |"
E_HELP = lines(
    "Here's what I understand:",
    "- `@carbon-room close <Month> [<YYYY>]`: start a month's close",
    "- `@carbon-room status`: show the current figures",
    "- `@carbon-room resume`: repost where the close stands",
    "- `@carbon-room publish`: publish the report (Lead only)",
    "- `@reporter draft`: draft the report",
    "- `@reporter trace <tag>`: show where one figure came from",
    "- `@reporter verify audit`: check the audit chain",
    "- `@<agent> <question>`: ask about the ledger",
    "",
    "In a gap thread, reply with one of the options it lists. "
    "If threads don't work, type `G-<n> <option>` anywhere in the room.",
)


def test_t_rounding_half_up():
    assert t(Decimal("50")) == "0.1 tCO2e"
    assert t(Decimal("49")) == "0.0 tCO2e"
    assert t(Decimal("22900")) == "22.9 tCO2e"
    assert t(Decimal("-50")) == "-0.1 tCO2e"


def test_t_handles_none_and_large():
    assert t(None) == "n/a"
    assert t(Decimal("1234567")) == "1,234.6 tCO2e"
    assert t(0) == "0.0 tCO2e"
    assert t(Decimal("0")) == "0.0 tCO2e"


def test_t_rejects_float():
    with pytest.raises(TypeError):
        t(1.5)
    with pytest.raises(TypeError):
        t(True)
    with pytest.raises(TypeError):
        pct(0.5)


def test_t_value_and_pct():
    assert t_value(Decimal("29.184")) == "29.2 tCO2e"
    assert t_value(Decimal("1234.56")) == "1,234.6 tCO2e"
    assert pct(Decimal("61")) == "61%"
    assert pct(Decimal("12.5")) == "13%"
    assert pct(Decimal("1E+2")) == "100%"
    assert pct(None) == "n/a"


def test_month_label_and_month_of():
    assert month_label("2026-10") == "October 2026"
    assert month_label("2025-01") == "January 2025"
    assert month_of("2026-10-v1") == "2026-10"
    assert month_of("2026-10-v12") == "2026-10"
    with pytest.raises(ValueError):
        month_label("bad")


def test_close_plan():
    assert close_plan("October 2026", "2026-10-v1", NAMES, "FS-2026-10") == E_PLAN


def test_handoffs():
    assert handoff_collect("October 2026", NAMES) == (
        "Collect October 2026 for HQ, Warehouse-2, Data Centre EU-West.")
    assert handoff_check("October 2026") == "Check October 2026: every rule, every claim."


def test_collector_statement():
    report = IngestReport("2026-10-v1", 9, [], [], "All 5 October sources collected.")
    assert collector_statement(report) == "All 5 October sources collected."
    failed = replace(report, failed_sources=["SRC-0003", "SRC-0004"])
    assert collector_statement(failed) == "All 5 October sources collected.\nCould not read 2 file(s)."


def test_gap_root_conflict_shows_both_excerpts_and_both_options():
    _, _, findings, gaps = scenario()
    assert gap_root(gaps[1], findings[1], "@lead") == E_G2


def test_gap_root_upload_has_hint():
    _, _, findings, gaps = scenario()
    assert gap_root(gaps[0], findings[0], "@priya") == E_G1
    assert UPLOAD_HINT in E_G1


def test_gap_root_reject_renders_reason():
    _, _, findings, gaps = scenario()
    assert gap_root(gaps[2], findings[2], "@lead") == E_G3


def test_gap_root_without_options_is_informational():
    _, _, findings, _ = scenario()
    gap = Gap("G-5", "2026-10-v1", "F-0000000006", "R6", "DATACENTRE",
              "Data centre invoice has no per-model AI breakdown", "lead", "OPEN", ["CL-0001"], [], None,
              "2026-11-06T16:00:00Z", None, None, None)
    assert gap_root(gap, findings[4], "@lead", fallback_hint=True) == E_G5


def test_gap_root_without_finding_omits_evidence():
    _, _, _, gaps = scenario()
    assert gap_root(gaps[3], None, "@lead") == E_G4_NOEV


def test_gap_root_fallback_hint():
    _, _, findings, gaps = scenario()
    assert gap_root(gaps[1], findings[1], "@lead", fallback_hint=True) == (
        E_G2 + "\n\nOr type `G-2 pick A` anywhere in the room.")


def test_options_help():
    _, _, _, gaps = scenario()
    assert options_help(gaps[1]) == "I didn't catch that. Reply with one of: `pick A`, `pick B`."
    assert options_help(gaps[2]) == (
        "I didn't catch that. Reply with one of: `approve`, `reject <reason>`.")


def test_short_replies():
    _, _, _, gaps = scenario()
    assert already_resolved(gaps[1]) == "G-2 is already resolved."
    assert checking() == "Checking…"
    assert outcome_resolved(gaps[1]) == "Resolved. G-2 is closed and the ledger is updated."
    assert outcome_open(gaps[0], "the next check still flags it") == (
        "G-1 is still open: the next check still flags it.")
    assert outcome_open(gaps[0], "Billing period still September.") == (
        "G-1 is still open: Billing period still September.")
    assert old_close_gap(gaps[1]) == (
        "G-2 belongs to an earlier close (2026-10-v1). Reply in the thread from the current close.")


def test_summary_post_refusal():
    fc, cid, _, _ = scenario()
    assert summary_post("October 2026", fc.summary(cid), D) == E_SUM_OPEN


def test_summary_post_numbers_are_formatted_from_summary():
    fc, cid, _, _ = scenario()
    g1(fc)
    assert summary_post("October 2026", fc.summary(cid), D) == E_SUM_G1


def test_summary_post_ready():
    fc, cid, _, _ = scenario()
    resolve_all(fc)
    assert summary_post("October 2026", fc.summary(cid), D) == E_SUM_READY


def test_summary_post_without_dc_line():
    fc, cid, _, _ = scenario()
    s = replace(fc.summary(cid), dc_line=None)
    assert summary_post("October 2026", s, D) == E_SUM_OPEN.rsplit("\n", 1)[0]


def test_dc_line():
    fc, cid, _, _ = scenario()
    assert dc_line(fc.summary(cid).dc_line) == E_DC


def test_total_moved():
    fc, cid, _, _ = scenario()
    s0 = fc.summary(cid)
    g1(fc)
    s1 = fc.summary(cid)
    assert total_moved(s0, s1) == "Total moved 0.0 → 3.6 tCO2e, coverage 0% → 12%."
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    fc.resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})
    s3 = fc.summary(cid)
    fc.resolve("G-4", "approve", LEAD, "h-5", {})
    s4 = fc.summary(cid)
    assert total_moved(s3, s4) == "Total moved 13.2 → 22.9 tCO2e, coverage 58% → 100%."


def test_draft_with_open_gaps():
    fc, cid, _, _ = scenario()
    assert draft(fc.draft_report(cid), "October 2026") == E_DRAFT_OPEN


def test_draft_after_all_resolutions():
    fc, cid, _, _ = scenario()
    resolve_all(fc)
    assert draft(fc.draft_report(cid), "October 2026") == E_DRAFT_DONE


def test_draft_one_tag_and_odd_items():
    fc, cid, _, _ = scenario()
    resolve_all(fc)
    report = replace(fc.draft_report(cid), s_tags=[replace(TAG, tag="S-007")], gaps=[{"x": 1}],
                     conflicts=[], compliance_flags=[], factor_versions=[], datacentre_line=None)
    out = draft(report, "October 2026")
    assert "- {'x': 1}" in out
    assert "Conflicts: none" in out
    assert "Compliance: none" in out
    assert "Factor versions: none" in out
    assert "1 source tag. Ask @reporter trace S-007 to see one." in out
    assert "Data centre:" not in out


def test_published():
    fc, cid, _, _ = scenario()
    resolve_all(fc)
    fc.draft_report(cid)
    report = fc.publish(cid, LEAD, "h-9")
    paths = ["out/2026-10/v1/coverage.html", "out/2026-10/v1/report.md"]
    assert published(report, "@lead", paths) == E_PUB


def test_published_with_open_gaps_and_no_files():
    fc, cid, _, _ = scenario()
    fc.draft_report(cid)
    report = fc.publish(cid, LEAD, "h-9")
    assert published(report, "@lead", []) == (
        "Published v1 by @lead.\n"
        "Verified: 0.0 tCO2e · Coverage: 0% · 0 of 4 expected sources verified\n"
        "Published with 4 open gap(s); their rows are excluded.\n"
        "Files: none written")


def test_trace_card_sha_is_12_chars():
    assert trace_card(TAG, "message h-5") == E_TRACE


def test_trace_card_tier1_no_link():
    out = trace_card(replace(TAG, approver=None, chat_message_id=None), None)
    assert out == E_TRACE.rsplit("\n", 1)[0] + "\nApproved by: Tier 1 (automatic)"


def test_audit_result_ok_and_broken():
    assert audit_result(AuditCheck(True, 57, None)) == "Audit chain intact: 57 events."
    assert audit_result(AuditCheck(False, 57, 12)) == "Audit chain broken at event 12 (57 events checked)."


def test_resume_line():
    fc, cid, _, _ = scenario()
    gaps = with_roots(fc, cid)
    assert resume_line("October 2026", "AWAITING_HUMANS", gaps, D, L) == E_RESUME
    no_root = [replace(gaps[0], thread_root_message_id=None), *gaps[1:]]
    assert resume_line("October 2026", "AWAITING_HUMANS", no_root, D, L) == E_RESUME.replace(
        "G-1 @priya (message m-3)", "G-1 @priya (no thread yet)")
    assert resume_line("October 2026", "AWAITING_HUMANS", [], D, L) == (
        "Resuming the October 2026 close at AWAITING_HUMANS.\nNo open gaps.")


def test_budget_lines():
    assert budget_warn("collector", "80%") == "@collector has used 80% of its budget for this close."
    assert budget_stopped("collector") == (
        "@collector has hit its budget for this close and has stopped. The Lead can raise it in config.")


def test_board():
    fc, cid, _, _ = scenario()
    with_roots(fc, cid)
    assert board("October 2026", fc.summary(cid), D, L) == E_BOARD


def test_board_no_gaps_and_pipe_escape():
    fc, cid, _, _ = scenario()
    open_summary = fc.summary(cid)
    resolve_all(fc)
    out = board("October 2026", fc.summary(cid), D, L)
    assert out.endswith("\n\nNo open gaps.")
    piped = replace(open_summary, open_gaps=[replace(open_summary.open_gaps[0], title="a | b",
                                                     thread_root_message_id=None)])
    assert board("October 2026", piped, D, L).splitlines()[-1] == E_PIPE


def test_simple_replies():
    assert no_close() == "No close has started yet. Start one with `@carbon-room close <Month>`."
    assert gap_not_found("G-9") == "I can't find an open G-9 in this close."
    assert tag_not_found("S-099") == "I can't find S-099 in this close."
    assert no_reply_needed() == "No reply needed here."


def test_help_text():
    assert help_text() == E_HELP
    assert help_text("I don't know the month 'Smarch'.") == "I don't know the month 'Smarch'.\n\n" + E_HELP


def _tree():
    return ast.parse(MODULE.read_text(encoding="utf-8"))


def test_messages_module_has_no_compute_calls():
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("sum", "float")
    inside_t = {id(n) for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "t"
                for n in ast.walk(f)}
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            assert id(node) in inside_t


def test_messages_imports_no_config_or_core():
    banned = ("carbon_room.config", "carbon_room.core", "carbon_room.ledger", "carbon_room.room.async_core")
    for node in ast.walk(_tree()):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            names += [f"{node.module}.{a.name}" for a in node.names]
        for name in names:
            assert not any(name == b or name.startswith(b + ".") for b in banned), name
