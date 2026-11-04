# Hand-offs

Each owner keeps their own section up to date. Shared contracts: `contracts/`.

---

## From Ujjwal (Ingestion & Ledger) → Richa and Akshar

**State:** schema, `db.py`, seed data with traps, collector, extraction with proof, consolidator, CLI and
tests are done on `feat/ingest` (PR #1). Design docs per feature: `docs/features/`. Run:

```bash
uv sync
uv run carbonroom seed                          # 11 docs -> 10 UNVERIFIED activities + 1 REC, 0 gaps
uv run carbonroom ledger show --period 2026-10
uv run pytest
```

No API key is needed: seed extractions are cached in `data/seed/extractions/`, and every cached value
is re-verified against its PDF on every run.

### Conventions everyone must follow

- **Only touch the ledger through `carbonroom.ledger.db`** (or read-only SQL). The database itself refuses
  `DELETE`, edits to evidence, closing a gap without a human, and closing a period without an `APPROVE`.
- **Quantities are decimal strings.** `Decimal(row["quantity"])`, or `db.activity_quantity(row)`. Never `float`
  (the helpers raise `LedgerError` on floats).
- Normalized units: electricity and cloud `kWh`, natural gas `therm`, diesel `gal` (US), RECs `MWh`.
- Rows come back as dicts. `*_json` columns are parsed and renamed: `aliases`, `meta`, `extra`, `refs`,
  `detail`; `quality_flags` is a list.
- Every helper logs to `events`. Pass `actor=` as your agent name (`cr-checker`, `cr-reporter`, ...).

### `carbonroom.ledger.db`: function list

| Area | Functions |
| --- | --- |
| Connection | `connect(path=None, create=True)`, `init_db`, `migrate`, `transaction(conn)`, `reset_db_file`, `log_event`, `list_events` |
| Values / ids | `dec`, `dec_str`, `sha256_text`, `dumps`, `loads`, `row_to_dict`, `make_doc_id`, `make_activity_id`, `make_instrument_id`; constants `ACTIVITY_STATUSES`, `ALLOWED_TRANSITIONS`, `GAP_KINDS`, `GAP_STATUSES`, `DOC_KINDS`; exception `LedgerError` |
| Sites / periods | `upsert_site`, `get_site`, `list_sites`, `match_sites`, `ensure_period`, `get_period`, `list_periods`, `set_period_factor_set`, `close_period(conn, period, approved_by=, actor=)` |
| Expected evidence | `upsert_expected_document`, `list_expected_documents`, `expected_but_missing(conn, period)` |
| Documents | `add_source_doc`, `get_source_doc`, `get_source_doc_by_sha`, `find_source_docs_by_ref`, `list_source_docs`, `update_source_doc_ref`, `mark_doc_superseded`, `current_doc` |
| Activities | `add_activity` (always `UNVERIFIED`), `get_activity`, `list_activities(period_id=, site_id=, category=, status=, include_superseded=, source_doc_id=)`, `activity_quantity`, `set_activity_status(conn, id, status, actor=, reason=)`, `supersede_activity(conn, old, new, actor=, reason=)`, `add_activity_note` |
| Instruments (RECs) | `add_instrument`, `get_instrument`, `list_instruments(period_id=)`, `set_instrument_quality_flags(conn, id, flags, actor=)`, `set_instrument_status` |
| Gaps | `create_gap(conn, kind=, detail=, created_by=, period_id=, site_id=, owner_handle=, room=, dedupe_key=, refs=)` → `(row, created)`, `get_gap`, `list_gaps`, `set_gap_thread`, `resolve_gap(conn, gap_id, resolution=, resolved_by=, status="RESOLVED")` |
| Approvals | `record_approval(conn, period_id=, approver_handle=, decision=, note=, report_sha256=)`, `list_approvals` |
| Factors / calcs | `add_emission_factor(**row)`, `list_emission_factors`, `add_calculation(activity_id=, factor_id=, scope=, co2e_kg=, code_version=)`, `list_calculations` (append-only: recompute = insert) |
| Export | `export_period(conn, period)` → the same JSON as `carbonroom ledger export` (`cr.ledger.v1`) |

Status rules (`ALLOWED_TRANSITIONS`): `UNVERIFIED → VERIFIED | FLAGGED | EXCLUDED`, `VERIFIED → FLAGGED | EXCLUDED`
(the false-done reopen), `FLAGGED → VERIFIED | UNVERIFIED | EXCLUDED`, `EXCLUDED → UNVERIFIED`. `SUPERSEDED` only
through `supersede_activity`, and it is final. `FLAGGED` and `EXCLUDED` need a reason.

### What an activity carries (`activity["extra"]`)

```text
original_quantity, original_unit, conversion   e.g. "14.62", "MWh", "MWh x 1000 = kWh"
doc_ref                                         e.g. "INV-204B"
proposer                                        "cache:llm:nvidia:nvidia/nemotron-3-ultra-550b-a55b" | "llm:<provider>:<model>" | "rules-v1"
evidence{site, period, doc_ref, <field>}        each {excerpt, locator, excerpt_sha256}
unverified_fields                               fields the document did not prove (each also has a gap)
diesel:        delivery_ref ("DLV-7731"), delivery_date
cloud_compute: pue ("1.35"), wue_l_per_kwh ("0.42"), cloud_region ("us-east-va")   <- quantity is IT kWh
electricity / natural_gas: meter_id
corrected bills: replaces_doc_ids, replaces_activity_ids
```

### For Richa: how each trap shows up, and the helper to use

| Trap | What the ledger has after `carbonroom seed` | Suggested checker step |
| --- | --- | --- |
| 1 Missing bill | no Reno `2026-10` electricity; `db.expected_but_missing(conn, "2026-10")` returns it with owner `lena`, room `cr-site-reno` | `create_gap(kind="missing_doc", ..., dedupe_key=f"missing:{site}:{category}:{period}")` |
| 2 Conflict | two Austin diesel rows for `2026-10`, both `extra["delivery_ref"] == "DLV-7731"`, 500 vs 550 gal, from INV-204 and INV-204B | group by `delivery_ref`; >1 distinct quantity → `kind="conflict"`, `refs={"activity_ids": [...]}` |
| 3 Stale factor | (yours: factor sets) | compare the factor's `set_version` with `periods.factor_set_version` (`set_period_factor_set` locks it) |
| 4 False done | after you mark the Austin Oct electricity row VERIFIED, `carbonroom ingest .../later/...ELB-AUS-2610-C.pdf` sets the original document's `superseded_by` and adds a new 196,800 kWh row with `replaces_activity_ids=[old id]`. **Ingestion leaves the old row as it is.** | `carbonroom.ingest.evidence.evidence_status(conn, activity_id)` → `source_superseded=True`, `excerpt_in_current_doc=False`, `replacement_activity_ids=[...]`. Reopen: `set_activity_status(old, "FLAGGED", reason=...)` + gap `excerpt_mismatch`; after Omar confirms: `supersede_activity(old, new, ...)` |
| 5 Outlier | Austin gas 4,800 → 7,700 therms (+60.4%) | compare the same site/category across periods |
| 6 Data centre + REC | cloud row: IT 38,200 kWh with `pue`, `wue_l_per_kwh` (page 2 evidence); one REC instrument: 120 MWh, `region="WECC Northwest (Oregon)"`, `vintage="2023"`, `site_id="nimbus-cloud"` (grid `SRVC`), `quality_flags=[]` | compare region with the site, vintage with the period → `set_instrument_quality_flags([...])` + gap `rec_quality` |

Other read helpers: `carbonroom.ingest.extract.excerpt_in_document(path, excerpt, page)`, `locator_page(locator)`,
`resolve_doc_path(path)`. Ingestion also opens `unverified_claim` gaps when a document doesn't prove a proposed
value (none in the seed data; see `tests/test_llm.py` for how one looks).

### For Akshar: getting room uploads into the ledger

**Option A (recommended): call the CLI right after downloading the attachment.** Synchronous, returns JSON.

```bash
carbonroom ingest /tmp/upload/reno-oct.pdf --from lena --room cr-site-reno \
  --thread <thread_id> --message <message_id> --gap GAP-012 --json
```

**Option C (for the orchestrator): a background batch run.** Many files, read in parallel, one final summary
to post. Nothing goes to chat until it finishes:

```bash
carbonroom ingest data/inbox --workers 4 --summary --json --run-id RUN-oct-close --period 2026-10
```

Post `summary_text` from the `cr.batch.v1` output. From Python or LangGraph, call
`carbonroom.ingest.batch.collect_node({"files": [...], "run_id": ..., "workers": 4})`, which returns
`{"ingest_summaries": [summary]}` (merge parallel branches with `operator.add`). Past runs: `carbonroom ledger runs`.
Details: `docs/features/batch-run.md`.

**Option B: the watch folder.** Drop the file at `data/inbox/<room>/<file>` with an optional sidecar
`data/inbox/<room>/<file>.meta.json`:

```json
{"received_from": "lena", "thread_id": "...", "message_id": "...", "gap_id": "GAP-012"}
```

and keep `carbonroom ingest --watch --json` running (it prints one JSON object per file and moves processed files
to `data/inbox/_processed/`). The room defaults to the folder name.

Output (`cr.ingest.v1`, one result per file; `status` is `new` or `duplicate`):

```json
{"file": "...", "sha256": "...", "status": "new", "doc_id": "DOC-73de8c54aefa", "kind": "utility_bill",
 "doc_ref": "ELB-RNO-2610", "proposer": "cache:llm:nvidia:nvidia/nemotron-3-ultra-550b-a55b", "site": "reno", "period": "2026-10",
 "received_from": "lena", "room": "cr-site-reno",
 "activities": [{"id": "ACT-dcfd7170bf", "category": "electricity", "quantity": "15080", "unit": "kWh",
                 "status": "UNVERIFIED", "excerpt": "Total energy used this period: 15.08 MWh",
                 "locator": "page=1;line=10", "excerpt_sha256": "...", "replaces_activity_ids": []}],
 "instruments": [], "gaps": [], "supersedes": []}
```

Suggested chat line: `[Ingested] ELB-RNO-2610 · Reno Office · 2026-10 · electricity 15,080 kWh (UNVERIFIED) · page 1, line 10`.
After you post a gap, record its thread with `db.set_gap_thread(conn, gap_id, thread_id, actor="cr-checker")`.

Handy for the demo and README: `carbonroom ledger show --period 2026-10`, `ledger missing`, `ledger gaps`,
`ledger events`, and `ledger verify` (re-hashes every document and re-finds every excerpt: "every number
traces back to a bill").

Adding your own CLI commands without touching `cli.py`: create one of `carbonroom/calc/cli.py`,
`carbonroom/check/cli.py`, `carbonroom/report/cli.py` or `carbonroom/switchbridge/cli.py` with a
`register(subparsers)` function; it is loaded automatically.

### For everyone: calling a model from your own agent code (model-agnostic)

```python
from carbonroom import llm

text, used = llm.chat([{"role": "user", "content": "Summarize GAP-012 for Lena"}], task="report")
data, used = llm.chat_json(messages, task="check")   # JSON reply, fences/<think> stripped
```

The model comes from settings, not code: `LLM_PROVIDER` + `LLM_MODEL`, or per task `LLM_MODEL_REPORT`,
`LLM_PROVIDER_CHECK`, ... Presets: nvidia, anthropic, openai, openrouter, ollama (local, no key), openai_compatible
(any server via `LLM_BASE_URL`). Other SDKs: `llm.register_provider(name, client_factory=...)`. Details:
`docs/features/llm.md`.

### Open questions for the team

1. Approve the additive schema columns in `contracts/CHANGES.md`.
2. September 2026 is loaded as `OPEN` and `UNVERIFIED`. If the demo should start with September already
   closed, the checker + Grace's approval need to run on it first (ingestion never verifies or closes).
3. Contract 5.4's gap example says "September electricity bill" for the October gap; it should say October.
