# Status

Each owner updates their own section: done / next / blocked.

## Ujjwal (Ingestion & Ledger), updated 2026-11-03 23:45 CT

**Done**
- `contracts/schema.sql` (Section 5.3, plus the additive columns in `contracts/CHANGES.md`) and `carbonroom/ledger/db.py`
- Fictional seed data with every document trap (`data/seed/README.md`); 2 documents held back in `data/seed/later/`
- Collector (sha256 dedupe, inbox watch folder with sidecars, content-addressed evidence store)
- Extraction with proof (cache / NVIDIA LLM / rules proposers; code verifies excerpt, number, unit, site, period)
- Consolidator (UNVERIFIED rows, both sides of conflicts kept, supersede links for corrected bills, `unverified_claim` gaps)
- CLI: `seed`, `ingest` (+ `--json`, `--watch`), `extract`, `ledger show|export|gaps|missing|events|verify`, `llm models|probe|bench`
- Tests: all passing (`uv run pytest`). Ingest is idempotent, and the seed is reproducible.
- `docs/HANDOFF.md`, `docs/EXPLAIN_ingestion.md`, `docs/DECISIONS.md`, `THIRD_PARTY.md`
- Feature docs (`docs/features/`) and a docs-drift test (`tests/test_docs.py`)
- LLM: `nvidia/nemotron-3-ultra-550b-a55b`, bench 13/13 exact (backup `nvidia/nemotron-3.5-bolt-e4b`, also 13/13); seed extractions re-saved with it

**Next**
- PR #1 (`feat/ingest`) is open: Akshar to review and merge
- Team sign-off on `contracts/CHANGES.md`
- Stretch, only after everything else works: Drive/email connectors using fictional files only

**Blocked**
- Nothing.

## Richa (Calculation, Checker & Report)

## Akshar (Switch Room, Demo & Submission)
