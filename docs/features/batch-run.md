# Background batch run

**Owner:** Ujjwal · **Code:** `carbonroom/ingest/batch.py` (+ `prepare`/`commit` in `carbonroom/ingest/pipeline.py`)
· **Tests:** `tests/test_batch.py`

## Why

The product: humans talk to one orchestrator agent in chat. When someone says "close October", the orchestrator
runs the specialist agents **in the background** (LangGraph, in parallel), keeps robot noise out of the team
channel, and reports back **once** with a final summary. For ingestion, that means:

- take a whole pile of files at once
- read them in parallel, because model calls are slow
- never let one bad file stop the run
- hand back one summary the orchestrator can post as-is

## Design

```mermaid
sequenceDiagram
  participant O as Orchestrator (LangGraph node / agent)
  participant B as batch.run_batch
  participant W as worker threads
  participant L as ledger
  O->>B: files, workers, run_id
  B->>L: batch_started event
  B->>B: hash every file; skip ones already in the ledger or repeated in the batch
  par prepare in parallel (no ledger access)
    B->>W: read text + propose (cache / model / rules)
  end
  loop fixed order (sorted paths)
    B->>L: verify + write one file per transaction
  end
  B->>L: batch_finished event (= the summary)
  B-->>O: cr.batch.v1 summary with summary_text
```

1. **Hash and dedupe on the main thread.** A file already in the ledger, or the same bytes twice in this batch,
   is a duplicate and costs no model call.
2. **Prepare in parallel** (`--workers N`): page text plus a proposal. This step never touches the ledger, so the
   slow model calls overlap. The rate limiter in `carbonroom/llm.py` is shared by all threads, so the total stays
   within `CR_LLM_RPM`.
3. **Commit in a fixed order** on the main thread: verify each file against its own text, then write it in one
   transaction. The order is sorted file paths (via `ThreadPoolExecutor.map`), so activity ids and `GAP-###` numbers
   are **identical with 1 worker or 8**.
4. **Failures are isolated.** A crash while preparing or committing one file goes into `errors` and an
   `ingest_error` event, and the run continues. Nothing half-written is left, so the next run picks that file up.
5. **One summary.** A `cr.batch.v1` summary is returned and stored in a `batch_finished` event (ref = run id).
   Every source document gets `meta.run_id`, so you can later ask what a given run collected.

### Summary (`cr.batch.v1`)

`run_id`, `started_at`, `finished_at`, `seconds`, `workers`, `files`, `new`, `duplicates`, `unreadable`, `failed`,
`errors[]`, `activities_count`, `instruments_count`, `activities[]` (id, site, period, category, quantity, unit,
one-line `summary`), `gaps[]`, `gaps_by_owner{handle: [GAP ids]}`, `expected_but_missing{period: [...]}` for every
period the run touched (plus `--period`), `periods`, `proposers{label: count}`, and **`summary_text`**, the line to
post. Example:

```text
Collected 11 new documents (0 duplicate, 0 unreadable, 0 failed) · 10 activities (all UNVERIFIED) and 1 REC ·
0 new gaps. Still missing: Reno Office electricity 2026-10 (@lena).
```

### LangGraph

`carbonroom.ingest.batch.collect_node` is a plain function (`state -> partial state`), so it works as a LangGraph
node, or as the target of `Send` for fan-out (say one branch per collector or per room). No LangGraph import is
needed in our code. It reads `files` and optionally `db_path`, `room`, `received_from`, `run_id`, `workers`,
`periods` and `proposer`. It returns `{"ingest_summaries": [summary]}`, a list, so parallel branches merge with
an `operator.add` reducer. Several branches can write to the same ledger file at once: SQLite WAL plus
`BEGIN IMMEDIATE` serialize the writes, and a test runs three nodes in parallel.

## Decisions

See `docs/DECISIONS.md`: parallel prepare, ordered commit; failures isolated; summary kept in the append-only
events log rather than a new table (no schema change); `collect_node` without a LangGraph dependency.

## Code map

| Name | Does |
| --- | --- |
| `carbonroom.ingest.batch.run_batch` | the whole run; returns `cr.batch.v1` |
| `carbonroom.ingest.batch.summarize` | builds the summary and `summary_text` |
| `carbonroom.ingest.batch.collect_node` | LangGraph-ready node |
| `carbonroom.ingest.batch.list_runs` | finished runs, newest first |
| `carbonroom.ingest.batch.get_run` | one run's stored summary |
| `carbonroom.ingest.pipeline.prepare` | read + propose, no ledger access (parallel-safe) |
| `carbonroom.ingest.pipeline.commit` | verify + write one prepared file (main thread) |

## Tests

`tests/test_batch.py`: the seed as one run (counts, missing Reno bill in `summary_text`, `meta.run_id`, stored
summary); same ids and gap numbers with 1 or 8 workers, including a duplicate and an unreadable file; preparation
really overlaps (peak concurrency above 1 and at most `workers`); one crashing file is isolated and picked up on
the next run; three parallel `collect_node` calls on one ledger file; the CLI's `--summary`, `--json`, `--period`
and `ledger runs`; plain `ingest` is unchanged without batch flags.

## Commands

| Command | Flags |
| --- | --- |
| `carbonroom ingest PATH... --workers N` | background batch (any of `--workers` above 1, `--summary`, `--run-id`, `--period` switches it on); `--summary` prints only the final summary (`--json` for `cr.batch.v1`); `--run-id ID` (default `RUN-...`); `--period YYYY-MM` also reports missing evidence for that month; plus every normal ingest flag |
| `carbonroom ledger runs` | `--id RUN-...` (one run's summary), `--limit` (default 20), `--json` |

## How to use

```bash
uv run carbonroom ingest data/inbox --workers 4 --summary
uv run carbonroom ingest data/inbox --workers 4 --summary --json --run-id RUN-oct-close --period 2026-10
uv run carbonroom ledger runs
uv run carbonroom ledger runs --id RUN-oct-close --json
```
