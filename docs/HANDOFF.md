# Handoff — from Richa (Calc/Check/Report) to Akshar (Switch/Demo) and Ujjwal (Ingest)

## Narration-to-implementation map

The richer demo story (Orchestrator, 5 Collectors, Gap Chaser, Compliance Checker, Finance
Reconciler, Verifier, etc.) is **demo narration over our existing 3-role build** — we agreed not
to build 11 separate agents in the time left. Here's what each story name actually calls:

| Story name | What it actually is |
|---|---|
| **Orchestrator** ("locks boundary, locks factor set, coordinates") | No new code. Just call `calc` → `check` → `report --draft` in sequence when a human types "close October." The "boundary lock" is just which `--period` you pass; the "factor lock" is `periods.factor_set_version` in the DB, already set by `seed-demo`. |
| **5 separate Collectors** (PDF/Email/Drive/Cloud/Travel) | Ujjwal's one Collector/Consolidator, narrated as if specialized. Not my scope either way. |
| **Calculator** | Exactly `carbonroom calc` / `carbonroom.calc.calculate_activity()`. |
| **Checker / Watchdog** | Exactly `carbonroom check` / `carbonroom.check.run_checks()`. Already does the "re-reads sources, posts gaps instead of a clean total" behavior the story describes. |
| **Gap Chaser** ("assigns + nudges owners in-thread") | No new logic. Every gap already has `owner_handle` + `room` — your agent just posts a reminder to that room periodically using data `check` already produced. Nothing to build on my side. |
| **Compliance Checker** ("framework flags / overclaim warnings") | **Not built.** If you want this in the demo, either fake it with a canned message, or tell me and I'll see what's realistic to add — it'd be new logic, not a relabeling. |
| **Finance Reconciler** ("cross-checks kWh against bill amounts") | **Not built**, and would need a `cost`/bill-amount field that doesn't exist in `contracts/schema.sql` today. Our existing `outlier` check (month-over-month %) covers the "flags one outlier" part of the story already — that's the realistic version to narrate. |
| **Verifier** ("tags every number to source, page, excerpt, factor, approver, e.g. `[S-014]`") | Already built. This *is* `build_report()`'s `evidence_index` — one entry per verified activity with `source_doc`, `excerpt`, `locator`, `sha256`. The `[S-014]`-style label is just a display convention you can apply when rendering; the underlying data already exists. |
| **Reporter** | Exactly `carbonroom report --publish` / `carbonroom.report.build_report()` + `publish_report()`. |

If you want any "✅ Not built" row made real, say so explicitly and we'll scope it — don't infer
new behavior from the story text, since none of it is implemented beyond what's listed above.

## To Akshar (Switch room, chat agents, demo)

### The CLI commands your agents should call

```
carbonroom seed-demo                                     # placeholder data, until Ujjwal's ingest is wired in
carbonroom calc    --period 2026-10 [--force]
carbonroom check   --period 2026-10
carbonroom resolve <gap_id> --answer "<reply text>" --by <handle>
carbonroom report  --period 2026-10 [--draft | --publish] [--out PATH]
carbonroom approve --period 2026-10 --by <handle> [--reject] [--note TEXT]
carbonroom ask "<question>" --period 2026-10
```

All commands take `--db <path>` (default `$CR_DB_PATH` or `./carbonroom.db`) so your agents can
point at the same SQLite file Ujjwal's ingestion writes into.

### Resolution reply formats your chat bot needs to forward verbatim into `resolve --answer`

These match the brief's Section 5.4 chat formats exactly:
- `"use <activity_id>"` or a bare number (`"1"`, `"2"`) — picks one candidate in a conflict,
  excludes the others.
- `"exclude: <reason>"` — excludes the one candidate activity this gap concerns.
- `"accept: <reason>"` — accepts the risk (used for outliers); closes the gap, changes nothing.
- `"approve"` (or a checkmark reaction mapped to the literal string `"approve"`) — sends a
  flagged activity (stale-factor, false-done) back to UNVERIFIED for re-verification.

`resolve` prints exactly what changed; have your agent post that back into the gap's thread.

### The report JSON your Reporter chat message should read from

`carbonroom report --period ... --draft` writes `report-<period>-draft.json` matching
`contracts/report.schema.json` field-for-field. The closing-slide fields you want for the demo's
final frame:
- `totals_t_co2e.scope1` / `.scope2_location` / `.scope2_market`
- `data_centre.co2e_location_t` / `.co2e_market_t` / `.rec_quality`
- `coverage_pct`
- `unverified_excluded_t_co2e`
- `gaps` (list of `{gap_id, kind, status, owner, resolution}`)

`render_markdown()` (also written to the sibling `.md` file) is a ready-to-post version in
roughly your `[Draft]`/`[Published]` chat template shape — feel free to reformat, the numbers are
the same either way.

### Gap message text your agent can post as-is (or reformat)

Every gap the Checker opens already has `kind`, `detail` (a full English sentence), `owner_handle`,
and `room` — printed directly by `carbonroom check`. Example from a real run:

```
[conflict] gap-2938a1f333d6 owner=omar room=cr-site-austin: 2 diesel activities disagree for
austin 2026-10: act-diesel-1=500gallon, act-diesel-2=550gallon
```

If you want the exact `[Gap] GAP-012 · Reno Office · ... @lena ...` format from Section 5.4,
you'll need to map `owner_handle` → `@mention` and `room` → the Switch room id yourself; I kept
the raw fields separate rather than guessing your template.

### What I have NOT built

- Any actual Switch/Mattermost posting — that's entirely yours.
- NLP-quality question parsing for `ask` — it's simple keyword matching on site names/categories.
  Fine for a scripted demo; if your agent does its own intent parsing, call
  `carbonroom.report.answer_question()` directly with the `site_id`/`category` you already
  extracted instead of relying on my keyword matcher.

## To Ujjwal (ingestion, ledger)

My code reads/writes exactly the tables in `contracts/schema.sql` — nothing more. Three things
that matter for a clean handoff when your real Collector/Consolidator replaces
`carbonroom/seed_demo.py`:

1. **`extra_json.delivery_id`** — my conflict check only groups activities that share an explicit
   `delivery_id` in `extra_json`. If your consolidator doesn't set this for multi-invoice
   categories (e.g. diesel), two genuinely conflicting invoices for the same delivery won't be
   caught. Categories with normally-one-document-per-month (electricity, natural gas) don't need
   this field.
2. **`extra_json.pue` / `.wue`** — required on any `cloud_compute` activity for the data-centre
   line to calculate at all. Missing either one isn't a crash — it becomes a `missing_pue`/
   `missing_wue` issue that the Calculator reports instead of guessing a default.
3. **`excerpt` / `excerpt_locator` / `excerpt_sha256` / `source_doc_id`** on every activity — the
   Reporter's evidence index (and the whole "every number traces to a source" pitch) is empty
   without these.

Everything else (site ids, period ids, status enum values) is exactly as written in
`contracts/schema.sql` — no changes needed on your side to match what I built.

## Open items for team agreement (not yet decided)

- Factor `id` naming scheme (`ef-elec-erct-loc-v1` style) — fine if nothing else names a factor,
  but flag it if your extraction/consolidation ever needs to reference one directly.
- `gap_activities` side table in `carbonroom/db.py` is **not** part of the shared
  `contracts/schema.sql` — it's CLI-local bookkeeping (which activities a gap concerns) so
  `resolve` knows its targets. If your real db layer replaces mine, you can keep this table,
  fold it into `gaps.detail` as JSON, or do it differently — just make sure `resolve` still has
  some way to know a gap's candidate activity ids.
