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
- `events` is a hash chain (the "Audit chain" box). Write events only with
  `log_event(conn, actor, action, ref, detail, chat_message_id=)`;
  a raw `INSERT` without the right `prev_event_hash` is refused by the database. Richa: this replaces
  `append_event(at=, actor=, action=, ref={...})` from the stand-in `carbonroom/db.py`: same column names
  (`prev_event_hash`, `event_hash`); put the id the event is about in `ref` and the rest of your dict in `detail`.
  Ids are integers (newest = highest), and `at` comes from the clock (`CR_NOW` pins it).
  Architecture "Event" contract → columns: `event_id` = `id`, `actor`, `claim_id` = `ref` (or any other id the
  event is about), `before_status`/`after_status`/`reason` = `detail["from"]`/`detail["to"]`/`detail["reason"]`
  (what `set_activity_status` logs), `chat_message_id`, `timestamp` = `at`, `prev_hash` = `prev_event_hash`,
  `hash` = `event_hash`.

### `carbonroom.ledger.db`: function list

| Area | Functions |
| --- | --- |
| Connection | `connect(path=None, create=True)`, `init_db`, `migrate`, `transaction(conn)`, `reset_db_file`, `log_event`, `list_events` |
| Audit chain | `event_hash(prev_event_hash, at, actor, action, ref, chat_message_id, detail_json)`, `audit_head(conn)` → newest `{id, at, actor, action, event_hash}`, `verify_audit_chain(conn)` → `{ok, events, broken, head, problems}` |
| Values / ids | `dec`, `dec_str`, `sha256_text`, `dumps`, `loads`, `row_to_dict`, `make_doc_id`, `make_activity_id`, `make_instrument_id`; constants `ACTIVITY_STATUSES`, `ALLOWED_TRANSITIONS`, `GAP_KINDS`, `GAP_STATUSES`, `DOC_KINDS`; exception `LedgerError` |
| Sites / periods | `upsert_site`, `get_site`, `list_sites`, `match_sites`, `ensure_period`, `get_period`, `list_periods`, `set_period_factor_set`, `close_period(conn, period, approved_by=, actor=)` |
| Closes (the "locks") | `start_close(conn, period, actor=, factor_set=, sites=, chat_message_id=)`, `get_close`, `get_open_close(conn, period)` (resume after a crash), `list_closes`, `set_close_phase(conn, close_id, phase, actor=, chat_message_id=, reason=)`, `publish_close(conn, close_id, published_by=, chat_message_id=, report_sha256=)`, `make_close_id`; constants `CLOSE_PHASES`, `PHASE_TRANSITIONS` |
| Expected evidence | `upsert_expected_document`, `list_expected_documents`, `expected_but_missing(conn, period, sites=)` (inside the close boundary) |
| Documents | `add_source_doc`, `get_source_doc`, `get_source_doc_by_sha`, `find_source_docs_by_ref`, `list_source_docs`, `update_source_doc_ref`, `mark_doc_superseded`, `current_doc` |
| Activities | `add_activity` (always `UNVERIFIED`), `get_activity`, `list_activities(period_id=, site_id=, category=, status=, include_superseded=, source_doc_id=)`, `activity_quantity`, `set_activity_status(conn, id, status, actor=, reason=, chat_message_id=)`, `supersede_activity(conn, old, new, actor=, reason=, chat_message_id=)`, `add_activity_note` |
| Instruments (RECs) | `add_instrument`, `get_instrument`, `list_instruments(period_id=)`, `set_instrument_quality_flags(conn, id, flags, actor=)`, `set_instrument_status` |
| Gaps | `create_gap(conn, kind=, detail=, created_by=, period_id=, site_id=, owner_handle=, room=, dedupe_key=, refs=, finding_id=)` → `(row, created)`, `get_gap`, `list_gaps`, `set_gap_thread`, `resolve_gap(conn, gap_id, resolution=, resolved_by=, chat_message_id=, status="RESOLVED")` |
| Approvals | `record_approval(conn, period_id=, approver_handle=, decision=, note=, report_sha256=, chat_message_id=)`, `list_approvals` |
| Factors / calcs | `add_emission_factor(**row)`, `list_emission_factors`, `add_calculation(activity_id=, factor_id=, scope=, co2e_kg=, code_version=)`, `list_calculations` (append-only: recompute = insert) |
| Export | `export_period(conn, period)` → the same JSON as `carbonroom ledger export` (`cr.ledger.v1`) |

Status rules (`ALLOWED_TRANSITIONS`): `UNVERIFIED → VERIFIED | FLAGGED | EXCLUDED`, `VERIFIED → FLAGGED | EXCLUDED`
(the false-done reopen), `FLAGGED → VERIFIED | UNVERIFIED | EXCLUDED`, `EXCLUDED → UNVERIFIED`. `SUPERSEDED` only
through `supersede_activity`, and it is final. `FLAGGED` and `EXCLUDED` need a reason.

### Closes and the room gate (architecture: "Close" contract, "Switch is load-bearing")

- `start_close` opens `CLOSE-<month>-v<N>` and **locks** its boundary (sites) and factor set: the database refuses
  to change either, and refuses a different `periods.factor_set_version` while the close is open. One open close
  per month; after a crash, `get_open_close(conn, month)` returns it and its `phase` (LangGraph state is a cache).
- Phases (`PHASE_TRANSITIONS`): OPEN to COLLECTING to CALCULATING to CHECKING; CHECKING to AWAITING_HUMANS or
  DRAFTED; AWAITING_HUMANS and RECHECKING go back and forth and on to DRAFTED; DRAFTED can go back to RECHECKING or
  AWAITING_HUMANS. Setting the same phase again is a no-op. PUBLISHED only through `publish_close`, and it is final;
  a correction is a new version (same factor set).
- **Every human action needs the Switch `chat_message_id` it came from**, checked by the database too:
  `record_approval` and `resolve_gap` refuse without one; `publish_close` needs the publisher's message **and** their
  `APPROVE` recorded from the room since this close started. The CLI has no approve/resolve/publish command
  (`tests/test_publish_needs_room.py`), so without the room there is only an unverified draft.
- Architecture contract → ledger: Close = `closes` row (`close_id` = `id`, `month` = `period_id`, `sites`,
  `factor_set`, `phase`, `version`, `published_by`, `published_message_id`). Gap = `gaps` row (`gap_id` = `id`,
  `finding_id`, `owner` = `owner_handle`, `status`, `thread_root_message_id` = `thread_id`, `opened_at` =
  `created_at`, `resolved_by`, `resolved_message_id`). Claim = `activities` row; the architecture's claim statuses
  map onto the ledger's: CONFLICTING and STALE = `FLAGGED` with an open `conflict` / `stale_factor` gap; MISSING =
  `expected_but_missing` (or a `missing_doc` gap); VERIFIED, UNVERIFIED and superseded are the same.

### What an activity carries (`activity["extra"]`)

```text
original_quantity, original_unit, conversion   e.g. "14.62", "MWh", "MWh x 1000 = kWh"
doc_ref                                         e.g. "INV-204B"
proposer                                        "cache:llm:nvidia:nvidia/nemotron-3-ultra-550b-a55b" | "llm:<provider>:<model>" | "rules-v1"
evidence{site, period, doc_ref, <field>}        each {excerpt, locator, excerpt_sha256}
unverified_fields                               fields the document did not prove (each also has a gap)
diesel:        delivery_ref ("DLV-7731"), delivery_date, delivery_id (= delivery_ref, the name calc/check read)
cloud_compute: pue ("1.35"), wue_l_per_kwh ("0.42"), wue (= wue_l_per_kwh, the name calc/check read),
               cloud_region ("us-east-va")   <- quantity is IT kWh
electricity / natural_gas: meter_id
corrected bills: replaces_doc_ids, replaces_activity_ids
```

### For Richa: how each trap shows up, and the helper to use

| Trap | What the ledger has after `carbonroom seed` | Suggested checker step |
| --- | --- | --- |
| 1 Missing bill | no Reno `2026-10` electricity; `db.expected_but_missing(conn, "2026-10")` returns it with owner `lena`, room `cr-site-reno` | `create_gap(kind="missing_doc", ..., dedupe_key=f"missing:{site}:{category}:{period}")` |
| 2 Conflict | two Austin diesel rows for `2026-10`, both `extra["delivery_id"] == "DLV-7731"` (also `delivery_ref`), 500 vs 550 gal, from INV-204 and INV-204B | group by `delivery_id`; >1 distinct quantity → `kind="conflict"`, `refs={"activity_ids": [...]}` |
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

### For everyone: the knowledge graph

The ledger is also a graph (live SQL views `ledger_nodes` / `ledger_edges`; `carbonroom.ledger.graph`):

- **"Where did this number come from?"** `graph.lineage(conn, "ACT-..." or "CALC-...")["text"]`, or
  `carbonroom ledger trace ACT-...`. Gives the excerpt, page/line, file hash, sender, room, model, corrections,
  calculation + factor, and open gaps. Ready to post as a chat answer, or to use for the report's evidence index.
- **"If this bill is wrong, what changes?"** `graph.impact(conn, "ELB-AUS-2610")["depends"]`, or
  `carbonroom ledger impact ELB-AUS-2610`. Useful for the false-done reopen.
- **Richa:** to link a gap to rows, put them in `refs` when you call `db.create_gap`: `activity_ids` (list),
  `activity_id`, `source_doc_id` or `instrument_id`. They become `about` edges automatically. This replaces the
  stand-in `gap_activities` side table in your branch.
- **Akshar:** `carbonroom ledger graph --period 2026-10 [--site austin] --out graph.md` draws a Mermaid graph for
  the README and video. Details: `docs/features/knowledge-graph.md`.

**The same graph in a graph database (Neo4j).** Start it once with
`docker compose -f infra/neo4j/docker-compose.yml up -d` (browser http://localhost:7474, user `neo4j`, password
`carbonroom-local`). From then on it updates by itself: **any** `carbonroom` command that writes to the ledger,
including your own plugin commands, re-syncs it. Nothing to change in your code, and if Neo4j isn't running
nothing breaks. If your code writes through `db.py` outside the CLI, call
`carbonroom.graphdb.store.sync_if_enabled(conn)` at the end.

- **Agents (Akshar):** `carbonroom graphdb why <site> <period> --json` answers "why didn't you consider X?" with a
  ready `summary` sentence. Also `graphdb conflicts`, `graphdb gaps` (open gaps per owner), `graphdb find "<text>"`,
  and read-only Cypher via `graphdb query`. For the video: the Cypher snippets in `docs/features/knowledge-graph.md`
  in Neo4j Browser.
- **Richa:** `graphdb conflicts` and `graphdb gaps` cross-check your checker; the ledger stays the source of truth.

### For everyone: calling a model from your own agent code (model-agnostic)

```python
from carbonroom import llm

text, used = llm.chat([{"role": "user", "content": "Summarize GAP-012 for Lena"}], task="report")
data, used = llm.chat_json(messages, task="check")   # JSON reply, fences/<think> stripped
```

To answer a person in plain words from ledger data (the architecture's "phrase"), build the message in code and
call `llm.phrase(message, question=...)`: it returns `.text` (the model's wording only if every number, id, month,
@handle and status word is unchanged; otherwise your message) and `.phrased`. Off unless `CR_PHRASE=auto`.
To cap spend, wrap your agent's work in `budgets.scope(conn, close_id, "cr-watchdog")` (`from carbonroom import
budgets`): every model call inside is charged to you for that close; at the cap calls raise
`llm.BudgetExceeded` (an `LLMError`), so keep a non-model fallback.

The model comes from settings, not code: `LLM_PROVIDER` + `LLM_MODEL`, or per task `LLM_MODEL_REPORT`,
`LLM_PROVIDER_CHECK`, ... Presets: nvidia, anthropic, openai, openrouter, ollama (local, no key), openai_compatible
(any server via `LLM_BASE_URL`). Other SDKs: `llm.register_provider(name, client_factory=...)`. Details:
`docs/features/llm.md`.

### Open questions for the team

1. Approve the additive schema columns in `contracts/CHANGES.md`.
2. September 2026 is loaded as `OPEN` and `UNVERIFIED`. If the demo should start with September already
   closed, the checker + Grace's approval need to run on it first (ingestion never verifies or closes).
3. Contract 5.4's gap example says "September electricity bill" for the October gap; it should say October.
