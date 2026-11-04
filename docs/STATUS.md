# Status

Each owner updates their own section: done / next / blocked.

## Ujjwal (Ingestion & Ledger), updated 2026-11-03 21:45 CT

**Done**
- `contracts/schema.sql` (Section 5.3, plus the additive columns in `contracts/CHANGES.md`) and `carbonroom/ledger/db.py`
- Fictional seed data with every document trap (`data/seed/README.md`); 2 documents held back in `data/seed/later/`
- Collector (sha256 dedupe, inbox watch folder with sidecars, content-addressed evidence store)
- Extraction with proof (cache / NVIDIA LLM / rules proposers; code verifies excerpt, number, unit, site, period)
- Consolidator (UNVERIFIED rows, both sides of conflicts kept, supersede links for corrected bills, `unverified_claim` gaps)
- CLI: `seed`, `ingest` (+ `--json`, `--watch`), `extract`, `ledger show|export|gaps|missing|events|verify`, `llm models|bench`
- Tests: all passing (`uv run pytest`). Ingest is idempotent, and the seed is reproducible.
- `docs/HANDOFF.md`, `docs/EXPLAIN_ingestion.md`, `docs/DECISIONS.md`, `THIRD_PARTY.md`

**Next**
- With an NVIDIA key: `carbonroom llm models`, then `carbonroom llm bench --models meta/llama-3.3-70b-instruct,nvidia/nemotron-3-super-120b-a12b,deepseek-ai/deepseek-v3.1`; record the winner; optionally `carbonroom seed --refresh-cache --proposer llm` to replace the rules-generated cache
- Open the PR `feat/ingest` → `main`, tagging Richa (db API) and Akshar (ingest hand-off)
- Team sign-off on `contracts/CHANGES.md`
- Stretch, only after everything else works: Drive/email connectors using fictional files only

**Blocked**
- Nothing. The NVIDIA key is a human step (build.nvidia.com → API Keys), and nothing needs it to run.

## Richa (Calculation, Checker & Report)

## Akshar (Switch Room, Demo & Submission)
