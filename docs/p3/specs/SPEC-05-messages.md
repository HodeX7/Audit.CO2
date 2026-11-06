# SPEC-05 · Message templates
Stories: P3-5.1 · Branch: `p3-s05-messages` · PR title: "P3-S05 (5.1): message templates"
Depends on (must be merged): SPEC-01 · Wave: 1 · Estimated session time: 1.5 h

> **Contract change (plan §3.9, edited in the same change as this spec)**
> 1. **New template `old_close_gap(gap)`.** SPEC-13 needs a reply for a thread reply whose gap belongs to an
>    earlier close. `core.resolve` always acts on the latest close, so such a reply must not reach it.
> 2. **Pinned copy.** The final strings below replace §3.9's starting copy, which the plan said this spec would
>    pin. Notable changes:
>    - `total_moved` is "Total moved 0.0 → 3.6 tCO2e, …", with the unit once.
>    - `published` adds an open-gaps line.
>    - `gap_root` adds an upload hint.
>    - Blank lines separate Markdown blocks, so Mattermost doesn't run lines into lists or quotes.

## 1. Goal
Write every message the room posts as a pure function: values in, `str` out. Templates format numbers that core
returned and never compute them. Exact snapshot tests keep the wording stable, so the demo, the README and the
video match.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.9 and §3.16
- `00-CONTRACTS.md` §2, §6 and §8
- `tests/fakes/fake_core.py` and `docs/p3/specs/SPEC-01-foundation.md` §7 (the fake scenario's exact titles,
  evidence and labels)

## 3. Files
- Create `carbon_room/room/messages.py`
- Create `tests/room/test_messages.py`

## 4. Public interface
```python
# helpers
def t(kg: Decimal | int | None) -> str
def t_value(tco2e: Decimal | int | None) -> str
def pct(p: Decimal | int | None) -> str
def month_label(month: str) -> str
def month_of(close_id: str) -> str

UPLOAD_HINT: str = "Attach the file to your reply, or put it in data/inbox/ and reply `upload <file name>`."

# templates
def close_plan(month_label: str, close_id: str, site_names: list[str], factor_set: str) -> str
def handoff_collect(month_label: str, site_names: list[str]) -> str
def handoff_check(month_label: str) -> str
def collector_statement(report: IngestReport) -> str
def gap_root(gap: Gap, finding: Finding | None, owner_display: str, *, fallback_hint: bool = False) -> str
def options_help(gap: Gap) -> str
def already_resolved(gap: Gap) -> str
def old_close_gap(gap: Gap) -> str
def checking() -> str
def outcome_resolved(gap: Gap) -> str
def outcome_open(gap: Gap, reason: str) -> str
def summary_post(month_label: str, summary: CloseSummary, display: Callable[[str], str]) -> str
def dc_line(dc: DcLine) -> str
def total_moved(before: CloseSummary, after: CloseSummary) -> str
def draft(report: Report, month_label: str) -> str
def published(report: Report, approver_display: str, paths: list[str]) -> str
def trace_card(tag: SourceTag, link: str | None) -> str
def audit_result(check: AuditCheck) -> str
def resume_line(month_label: str, phase: str, gaps: list[Gap], display: Callable[[str], str],
                link: Callable[[str], str]) -> str
def budget_warn(agent: str, warn_label: str) -> str
def budget_stopped(agent: str) -> str
def board(month_label: str, summary: CloseSummary, display: Callable[[str], str],
          link: Callable[[str], str]) -> str
def no_close() -> str
def gap_not_found(gap_id: str) -> str
def tag_not_found(tag: str) -> str
def no_reply_needed() -> str
def help_text(reason: str | None = None) -> str
```

## 5. Behaviour

### Helpers
1. **`t(kg)`**
   - None gives `"n/a"`.
   - A `float` (or any type other than `Decimal`/`int`) raises `TypeError("t() needs a Decimal")`. A `bool`
     counts as a wrong type.
   - Otherwise: `(Decimal(kg) / Decimal(1000)).quantize(Decimal("0.1"), ROUND_HALF_UP)`, formatted with
     `format(value, ",")`, then `" tCO2e"`.
   - Examples: `Decimal("22900")` → `"22.9 tCO2e"`; `Decimal("1234567")` → `"1,234.6 tCO2e"`;
     `Decimal("50")` → `"0.1 tCO2e"`; `Decimal("49")` → `"0.0 tCO2e"`; `Decimal("0")` → `"0.0 tCO2e"`.
2. **`t_value(tco2e)`** works the same for a figure already in tonnes, with no division.
   `Decimal("29.184")` → `"29.2 tCO2e"`.
3. **`pct(p)`**
   - None gives `"n/a"`, and a float raises `TypeError`.
   - Otherwise: `p.quantize(Decimal("1"), ROUND_HALF_UP)`, then `"%"`, formatted with `format(value, "f")` so
     that no exponent appears.
   - Examples: `Decimal("61")` → `"61%"`; `Decimal("12.5")` → `"13%"`; `Decimal("1E+2")` → `"100%"`.
4. **`month_label("2026-10")`** gives `"October 2026"`. It uses a fixed tuple of English month names, never
   `calendar` or the locale. A malformed month raises `ValueError`.
5. **`month_of("2026-10-v1")`** gives `"2026-10"`, via `close_id.rsplit("-v", 1)[0]`.
6. **Rendered option key.**
   - `render_key(option)` (private) is `"reject <reason>"` when `option.action == "reject"`, else `option.key`.
   - `site_names` and other lists are joined with `", "`.
   - The figures line is `f"Verified: {t(v)} · Excluded (not verified): {t(x)} · Coverage: {pct(c)}"`.
     The separator is ` · ` (U+00B7 with a space on each side).

### Purity rules
7. **No computing.** Templates never call core, never read config, and never compute a figure. `len()` of a list
   is allowed. The only division in the module is the one in `t`.
8. **Verbatim values.** Labels, titles, evidence, notes, flags and paths are printed exactly as given.
9. **Style.**
   - No emoji.
   - Markdown is limited to `**bold**`, `` `code` ``, `> quote`, `- ` lists, one `###` heading and a table (both
     only in `board`).
   - Blocks are joined with `"\n\n"`. Lines inside a block are joined with `"\n"`.
10. **Literals.** The module contains no site id (not even the letters `hq` inside a word or identifier), no
    `\d{4}-\d{2}` month, and no `CL-`/`G-`/`S-` followed by digits. Examples in docstrings must use
    placeholders.

### Template outputs
11. Each template returns exactly the text shown in §6 for the given inputs. The structure rules are:
    - **`collector_statement`:** `report.statement`. When `failed_sources` is non-empty, `\nCould not read {n}
      file(s).` follows.
    - **`gap_root`:**
      - Block 1 is the header `**{gap_id} · {kind}** {title}`, then `Owner: {owner_display}`. When `finding`
        is not None and its evidence is non-empty, `Evidence:` follows, then one `> {line}` per evidence line.
      - With options: block 2 is `Reply in this thread with:` and one `` - `{render_key}`: {label} `` per option.
        If any option has action `upload`, a block with `UPLOAD_HINT` follows. With `fallback_hint`, a final
        block `` Or type `{gap_id} {render_key(options[0])}` anywhere in the room. `` follows.
      - Without options: block 2 is `No reply needed. {owner_display} follows this up.`, with no fallback hint.
    - **`summary_post`:**
      - Line 1 is `I can't give a clean {month} total yet.` when `open_gaps` is non-empty, else
        `{month} is ready to draft.`
      - Then the figures line, then `Sources: {sv} of {se} expected sources verified.`
      - With gaps: `Open gaps ({n}): ` followed by `G-n {display(owner)}` items joined with ` · `.
      - When `dc_line` is set: the `dc_line` text.
      - Without gaps: `Next: @reporter draft` last.
      - All of this is one block (lines joined with `\n`).
    - **`dc_line`:** `Data centre: location-based {t(loc)} · market-based {t(mkt)} ({rec_flag}) · AI line
      {ai_line_status}: {note}`.
    - **`total_moved`:** `Total moved {n(b)} → {n(a)} tCO2e, coverage {pct(b)} → {pct(a)}.`, where `n(x)` is
      `t(x.verified_kgco2e)` without the `" tCO2e"` suffix.
    - **`draft`:**
      - Block 1: `**Draft v{version} for {month}**`, then
        `Verified: {t_value} · Excluded (not verified): {t_value} · Coverage: {pct} · {source_coverage}`.
      - Block: `Open and excluded:` with one `- {gap_id} {title}` per `report.gaps` item, or the single line
        `Open and excluded: none`.
      - Block: `Conflicts:` with items, or `Conflicts: none`. In both lists, an item with neither `gap_id` nor
        `title` renders as `- {str(item)}`.
      - The `dc_line` block, when present.
      - Block: `Compliance:` with `- {flag}` lines, or `Compliance: none`.
      - Last block: `Factor versions: {joined or "none"}`, then the tags line, then
        `The Lead publishes with @carbon-room publish.`
      - The tags line is `No verified lines yet, so there are no source tags.` when there are no tags;
        `1 source tag. Ask @reporter trace {tag} to see one.` for one; and
        `{n} source tags. Ask @reporter trace {first tag} to see one.` otherwise.
    - **`published`:**
      - `Published v{version} by {approver_display}.`
      - Then `Verified: {t_value} · Coverage: {pct} · {source_coverage}`.
      - When `report.gaps` is non-empty: `Published with {n} open gap(s); their rows are excluded.`
      - Then `Files: {joined paths}`, or `Files: none written`.
      - All of this is one block.
    - **`trace_card`:**
      ```
      {tag} · {activity} · {status}
      File: {file_name}, page {page}
      Excerpt: "{excerpt}"
      SHA-256: {sha256[:12]}…
      Factor: {factor_id} ({factor_version}, {geography})
      Recompute: {recompute}
      Result: {t(kgco2e)}
      Approved by: {approver or "Tier 1 (automatic)"}
      ```
      The last line gets ` · {link}` appended when `link` is not None.
    - **`resume_line`:** `Resuming the {month} close at {phase}.`, then either `No open gaps.` or
      `Open gaps: ` followed by items joined with ` · `. Each item is `{gap_id} {display(owner)} ({link(root)})`,
      or `… (no thread yet)` when the root is None.
    - **`board`:**
      - Block 1: `### Close Board · {month}`, `Phase: {phase}`, the figures line, and the Sources line.
      - Block 2: either `No open gaps.` or the table. The table header is `| Gap | Owner | Status | Thread |`,
        then `|---|---|---|---|`, then one row per open gap:
        `| {gap_id} {title} | {display(owner)} | {status} | {link(root) or "none"} |`. Every `|` inside a cell
        is replaced with `\|`.
    - **`help_text`:** when `reason` is given, the reason is the first block. The command block follows, then the
      thread block (exact text in §6).

## 6. Test plan
**Shared arrange (module-level helpers in `test_messages.py`):**
- `scenario()` runs `FakeCore` start (`"2026-10"`, the three site ids, `"FS-2026-10"`, a lead actor, `"h-1"`),
  then ingest, calculate and check. It returns `(fc, cid, findings, gaps)`, where `gaps` is
  `fc.resume_state(cid)[1]` (G-1…G-4).
- `D = lambda pid: f"@{pid}"` and `L = lambda mid: f"message {mid}"`.
- `NAMES = ["HQ", "Warehouse-2", "Data Centre EU-West"]`.
- `DC` is the exact dc_line text, E-DC below.
- `resolve_all(fc, cid)` plays the four resolutions in SPEC-01's `test_fake_resolutions_follow_table`.

Each test asserts `==` against the exact expected string. The `E-…` blocks below are the exact strings: each line
is joined with `\n`, and a blank line is an empty line.

| Test | Act | Expected |
|---|---|---|
| `test_t_rounding_half_up` | `t(Decimal("50"))`, `t(Decimal("49"))`, `t(Decimal("22900"))`, `t(Decimal("-50"))` | `"0.1 tCO2e"`, `"0.0 tCO2e"`, `"22.9 tCO2e"`, `"-0.1 tCO2e"` [1] |
| `test_t_handles_none_and_large` | `t(None)`, `t(Decimal("1234567"))`, `t(0)`, `t(Decimal("0"))` | `"n/a"`, `"1,234.6 tCO2e"`, `"0.0 tCO2e"`, `"0.0 tCO2e"` [1] |
| `test_t_rejects_float` | `t(1.5)`, `t(True)`, `pct(0.5)` | each raises `TypeError` [1, 3] |
| `test_t_value_and_pct` | `t_value(Decimal("29.184"))`, `t_value(Decimal("1234.56"))`, `pct(Decimal("61"))`, `pct(Decimal("12.5"))`, `pct(Decimal("1E+2"))`, `pct(None)` | `"29.2 tCO2e"`, `"1,234.6 tCO2e"`, `"61%"`, `"13%"`, `"100%"`, `"n/a"` [2, 3] |
| `test_month_label_and_month_of` | `month_label("2026-10")`, `month_label("2025-01")`, `month_of("2026-10-v1")`, `month_of("2026-10-v12")`, `month_label("bad")` | `"October 2026"`, `"January 2025"`, `"2026-10"`, `"2026-10"`, raises `ValueError` [4, 5] |
| `test_close_plan` | `close_plan("October 2026", "2026-10-v1", NAMES, "FS-2026-10")` | E-PLAN |
| `test_handoffs` | `handoff_collect("October 2026", NAMES)`, `handoff_check("October 2026")` | `"Collect October 2026 for HQ, Warehouse-2, Data Centre EU-West."`, `"Check October 2026: every rule, every claim."` |
| `test_collector_statement` | `collector_statement(IngestReport("2026-10-v1", 9, [], [], "All 5 October sources collected."))`, then the same with `failed_sources=["SRC-0003", "SRC-0004"]` | `"All 5 October sources collected."`, `"All 5 October sources collected.\nCould not read 2 file(s)."` |
| `test_gap_root_conflict_shows_both_excerpts_and_both_options` | `gap_root(gaps[1], findings[1], "@lead")` | E-G2 |
| `test_gap_root_upload_has_hint` | `gap_root(gaps[0], findings[0], "@priya")` | E-G1 |
| `test_gap_root_reject_renders_reason` | `gap_root(gaps[2], findings[2], "@lead")` | E-G3 |
| `test_gap_root_without_options_is_informational` | a `Gap("G-5", cid, "F-0000000006", "R6", "DATACENTRE", "Data centre invoice has no per-model AI breakdown", "lead", "OPEN", ["CL-0001"], [], None, "2026-11-06T16:00:00Z", None, None, None)` and `findings[4]`, with `fallback_hint=True` | E-G5 |
| `test_gap_root_without_finding_omits_evidence` | `gap_root(gaps[3], None, "@lead")` | E-G4-NOEV |
| `test_gap_root_fallback_hint` | `gap_root(gaps[1], findings[1], "@lead", fallback_hint=True)` | E-G2, then `"\n\nOr type `G-2 pick A` anywhere in the room."` |
| `test_options_help` | `options_help(gaps[1])`, `options_help(gaps[2])` | ``"I didn't catch that. Reply with one of: `pick A`, `pick B`."``, ``"I didn't catch that. Reply with one of: `approve`, `reject <reason>`."`` |
| `test_short_replies` | `already_resolved(gaps[1])`, `checking()`, `outcome_resolved(gaps[1])`, `outcome_open(gaps[0], "the next check still flags it")`, `outcome_open(gaps[0], "Billing period still September.")`, `old_close_gap(gaps[1])` | `"G-2 is already resolved."`, `"Checking…"` (U+2026), `"Resolved. G-2 is closed and the ledger is updated."`, `"G-1 is still open: the next check still flags it."`, `"G-1 is still open: Billing period still September."`, `"G-2 belongs to an earlier close (2026-10-v1). Reply in the thread from the current close."` |
| `test_summary_post_refusal` | `summary_post("October 2026", fc.summary(cid), D)` | E-SUM-OPEN |
| `test_summary_post_numbers_are_formatted_from_summary` | after the G-1 upload only | E-SUM-G1 |
| `test_summary_post_ready` | after `resolve_all` | E-SUM-READY |
| `test_summary_post_without_dc_line` | a copy of the after-check summary with `dc_line=None` | E-SUM-OPEN without its last line |
| `test_dc_line` | `dc_line(fc.summary(cid).dc_line)` | E-DC |
| `test_total_moved` | `total_moved(s0, s1)` for the summaries before and after the G-1 upload; then after G-3 and after G-4 | `"Total moved 0.0 → 3.6 tCO2e, coverage 0% → 12%."`; `"Total moved 13.2 → 22.9 tCO2e, coverage 58% → 100%."` |
| `test_draft_with_open_gaps` | `draft(fc.draft_report(cid), "October 2026")` right after check | E-DRAFT-OPEN |
| `test_draft_after_all_resolutions` | `resolve_all`, then `draft(fc.draft_report(cid), "October 2026")` | E-DRAFT-DONE |
| `test_draft_one_tag_and_odd_items` | a `Report` copy with `s_tags` of one tag (`tag="S-007"`), `gaps=[{"x": 1}]`, `conflicts=[]`, `compliance_flags=[]`, `factor_versions=[]`, `datacentre_line=None` | contains `"- {'x': 1}"`, `"Conflicts: none"`, `"Compliance: none"`, `"Factor versions: none"`, `"1 source tag. Ask @reporter trace S-007 to see one."`, and no `"Data centre:"` |
| `test_published` | `resolve_all`, draft, then `published(fc.publish(cid, LEAD, "h-9"), "@lead", ["out/2026-10/v1/coverage.html", "out/2026-10/v1/report.md"])` | E-PUB |
| `test_published_with_open_gaps_and_no_files` | draft right after check, then `fc.publish`; `published(report, "@lead", [])` | `"Published v1 by @lead.\nVerified: 0.0 tCO2e · Coverage: 0% · 0 of 4 expected sources verified\nPublished with 4 open gap(s); their rows are excluded.\nFiles: none written"` |
| `test_trace_card_sha_is_12_chars` | `trace_card(TAG, "message h-5")`, where `TAG` is §7's SourceTag | E-TRACE |
| `test_trace_card_tier1_no_link` | `trace_card(replace(TAG, approver=None, chat_message_id=None), None)` | E-TRACE with the last line `"Approved by: Tier 1 (automatic)"` |
| `test_audit_result_ok_and_broken` | `audit_result(AuditCheck(True, 57, None))`, `audit_result(AuditCheck(False, 57, 12))` | `"Audit chain intact: 57 events."`, `"Audit chain broken at event 12 (57 events checked)."` |
| `test_resume_line` | gaps G-1…G-4 with roots `m-3`…`m-6` (set with `fc.record_gap_thread`), then `resume_line("October 2026", "AWAITING_HUMANS", gaps, D, L)`; again with G-1's root None; again with `[]` | E-RESUME; the same with `"G-1 @priya (no thread yet)"`; `"Resuming the October 2026 close at AWAITING_HUMANS.\nNo open gaps."` |
| `test_budget_lines` | `budget_warn("collector", "80%")`, `budget_stopped("collector")` | `"@collector has used 80% of its budget for this close."`, `"@collector has hit its budget for this close and has stopped. The Lead can raise it in config."` |
| `test_board` | roots as in `test_resume_line`; `board("October 2026", fc.summary(cid), D, L)` | E-BOARD |
| `test_board_no_gaps_and_pipe_escape` | after `resolve_all`; and a copy of the after-check summary whose `open_gaps` is one copy of G-1 with title `a PIPE b` (PIPE is the `\|` character) and root None | the first ends with `"\n\nNo open gaps."`; the second's table row is E-PIPE |
| `test_simple_replies` | `no_close()`, `gap_not_found("G-9")`, `tag_not_found("S-099")`, `no_reply_needed()` | ``"No close has started yet. Start one with `@carbon-room close <Month>`."``, `"I can't find an open G-9 in this close."`, `"I can't find S-099 in this close."`, `"No reply needed here."` |
| `test_help_text` | `help_text()`, `help_text("I don't know the month 'Smarch'.")` | E-HELP; `"I don't know the month 'Smarch'.\n\n" + E-HELP` |
| `test_messages_module_has_no_compute_calls` | parse `carbon_room/room/messages.py` with `ast` | no `ast.Call` to the names `sum` or `float`; every `ast.BinOp` with `ast.Div` lies inside the `FunctionDef` named `t` [7] |
| `test_messages_imports_no_config_or_core` | the same AST | no import of `carbon_room.config`, `carbon_room.core`, `carbon_room.ledger` or `carbon_room.room.async_core` [7] |

**Exact expected strings**

E-PLAN
```
Starting the October 2026 close (2026-10-v1).
Sites: HQ, Warehouse-2, Data Centre EU-West. Factor set FS-2026-10 is locked.
Plan: @collector gathers the sources, I calculate, @watchdog checks every row. Anything that fails a check becomes a thread with an owner.
```

E-G1
```
**G-1 · PERIOD** Warehouse-2 October bill is a September bill
Owner: @priya
Evidence:
> File name: warehouse2_electricity_2026-10.pdf
> Billing period: 1–30 Sep 2026

Reply in this thread with:
- `upload`: Upload the October bill

Attach the file to your reply, or put it in data/inbox/ and reply `upload <file name>`.
```

E-G2
```
**G-2 · CONFLICTING** HQ October diesel has two invoices 400 L apart
Owner: @lead
Evidence:
> Invoice 4471: Diesel delivered: 2000 L
> Invoice 4471-rev: Diesel delivered: 2400 L

Reply in this thread with:
- `pick A`: Invoice 4471 — 2,000 L
- `pick B`: Invoice 4471-rev — 2,400 L
```

E-G3
```
**G-3 · STALE** Data centre invoice uses last year's Ember factor
Owner: @lead
Evidence:
> vendor_factor_ref: Ember 2024 IE
> Locked factor set FS-2026-10 uses Ember 2025

Reply in this thread with:
- `approve`: Use the locked Ember 2025 IE factor
- `reject <reason>`: Exclude the cloud line
```

E-G4-NOEV
```
**G-4 · VARIANCE** HQ October electricity is 38% above September
Owner: @lead

Reply in this thread with:
- `approve`: Accept +38% against September
- `reject <reason>`: Exclude HQ electricity
```

E-G5
```
**G-5 · DATACENTRE** Data centre invoice has no per-model AI breakdown
Owner: @lead
Evidence:
> ai_breakdown: none on the invoice

No reply needed. @lead follows this up.
```

E-DC (one line)
```
Data centre: location-based 4.3 tCO2e · market-based 0.0 tCO2e (Market-based 0 relies on certificates; certificate quality not verified) · AI line UNVERIFIED: No per-model AI breakdown on the invoice.
```

E-SUM-OPEN
```
I can't give a clean October 2026 total yet.
Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0%
Sources: 0 of 4 expected sources verified.
Open gaps (4): G-1 @priya · G-2 @lead · G-3 @lead · G-4 @lead
<E-DC>
```

E-SUM-G1
```
I can't give a clean October 2026 total yet.
Verified: 3.6 tCO2e · Excluded (not verified): 25.7 tCO2e · Coverage: 12%
Sources: 1 of 4 expected sources verified.
Open gaps (3): G-2 @lead · G-3 @lead · G-4 @lead
<E-DC>
```

E-SUM-READY
```
October 2026 is ready to draft.
Verified: 22.9 tCO2e · Excluded (not verified): 0.0 tCO2e · Coverage: 100%
Sources: 4 of 4 expected sources verified.
<E-DC>
Next: @reporter draft
```

E-DRAFT-OPEN
```
**Draft v1 for October 2026**
Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0% · 0 of 4 expected sources verified

Open and excluded:
- G-1 Warehouse-2 October bill is a September bill
- G-2 HQ October diesel has two invoices 400 L apart
- G-3 Data centre invoice uses last year's Ember factor
- G-4 HQ October electricity is 38% above September

Conflicts:
- G-2 HQ October diesel has two invoices 400 L apart

<E-DC>

Compliance:
- Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero

Factor versions: DEFRA 2026, EGRID 2024, EMBER 2025
No verified lines yet, so there are no source tags.
The Lead publishes with @carbon-room publish.
```

E-DRAFT-DONE
```
**Draft v1 for October 2026**
Verified: 22.9 tCO2e · Excluded (not verified): 0.0 tCO2e · Coverage: 100% · 4 of 4 expected sources verified

Open and excluded: none

Conflicts: none

<E-DC>

Compliance:
- Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero

Factor versions: DEFRA 2026, EGRID 2024, EMBER 2025
4 source tags. Ask @reporter trace S-001 to see one.
The Lead publishes with @carbon-room publish.
```

E-PUB
```
Published v1 by @lead.
Verified: 22.9 tCO2e · Coverage: 100% · 4 of 4 expected sources verified
Files: out/2026-10/v1/coverage.html, out/2026-10/v1/report.md
```

E-TRACE
```
S-001 · electricity_kwh · VERIFIED
File: hq_electricity_2026-10.pdf, page 1
Excerpt: "Total consumption: 48300 kWh"
SHA-256: 4c1d8e2a9b70…
Factor: EGRID-2024-CAMX (2024, CAMX)
Recompute: 48300 kWh × 0.2 kgCO2e/kWh = 9660 kgCO2e
Result: 9.7 tCO2e
Approved by: lead · message h-5
```

E-RESUME
```
Resuming the October 2026 close at AWAITING_HUMANS.
Open gaps: G-1 @priya (message m-3) · G-2 @lead (message m-4) · G-3 @lead (message m-5) · G-4 @lead (message m-6)
```

E-BOARD
```
### Close Board · October 2026
Phase: AWAITING_HUMANS
Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0%
Sources: 0 of 4 expected sources verified.

| Gap | Owner | Status | Thread |
|---|---|---|---|
| G-1 Warehouse-2 October bill is a September bill | @priya | OPEN | message m-3 |
| G-2 HQ October diesel has two invoices 400 L apart | @lead | OPEN | message m-4 |
| G-3 Data centre invoice uses last year's Ember factor | @lead | OPEN | message m-5 |
| G-4 HQ October electricity is 38% above September | @lead | OPEN | message m-6 |
```

E-PIPE (the backslash is a real character in the output)
```
| G-1 a \| b | @priya | OPEN | none |
```

E-HELP
```
Here's what I understand:
- `@carbon-room close <Month> [<YYYY>]`: start a month's close
- `@carbon-room status`: show the current figures
- `@carbon-room resume`: repost where the close stands
- `@carbon-room publish`: publish the report (Lead only)
- `@reporter draft`: draft the report
- `@reporter trace <tag>`: show where one figure came from
- `@reporter verify audit`: check the audit chain
- `@<agent> <question>`: ask about the ledger

In a gap thread, reply with one of the options it lists. If threads don't work, type `G-<n> <option>` anywhere in the room.
```

Write each expected string in the test file as a parenthesised sequence of string literals, or as
`"\n".join([...])`. Substitute `<E-DC>` with the E-DC line.

## 7. Fixtures and doubles
- `FakeCore` (SPEC-01).
- `TAG = SourceTag("S-001", "hq_electricity_2026-10.pdf", 1, "Total consumption: 48300 kWh",
  "4c1d8e2a9b70" + "0" * 52, "electricity_kwh", Decimal("48300"), "kWh", "EGRID-2024-CAMX", "2024", "CAMX",
  "48300 kWh × 0.2 kgCO2e/kWh = 9660 kgCO2e", Decimal("9660"), "VERIFIED", "lead", "h-5")`
- `LEAD = Actor("human", "lead", "Sustainability Lead", "lead")`, `PRIYA = Actor("human", "priya", "Priya",
  "site_manager")`

## 8. Manual check
After SPEC-15 merges: run a close in the real room and look at each post in Mattermost. Quotes, lists and the
board table should render, with no list or quote swallowing the next line.

## 9. Done when
- [ ] Each template has a snapshot test
- [ ] The diesel conflict's gap root shows both excerpts and both options
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Deciding when or where to post. The handlers do that (SPEC-12 to SPEC-14).
- Error texts (SPEC-04). `budget_stopped` repeats the `BudgetExceeded` sentence on purpose, so the two modules
  stay independent.

## 11. Open questions
None block execution. Q4 in plan §1.4 (`Report.gaps` shape) is handled by rendering `gap_id` and `title` when
present and the raw item otherwise.
