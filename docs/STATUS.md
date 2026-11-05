# Status

Each owner updates their own section: done / next / blocked.

## Ujjwal (Ingestion & Ledger), updated 2026-11-04 15:50 CT

**Current P1 integration**
- Room-resume helpers and single-file room ingestion are implemented in `core.py`, including an audit-linked human `chat_message_id`.

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
- Model-agnostic LLM layer (any provider, per-task models, pluggable SDKs)
- Background batch run for the orchestrator: parallel, one final summary, `collect_node` for LangGraph
- Knowledge graph: live graph views, `ledger trace` (where did this number come from?), `ledger impact` (what depends on this bill?), `ledger graph` (Mermaid/JSON)
- Same graph mirrored into Neo4j (graph database), auto-synced: `graphdb why` / `conflicts` / `gaps` / `find` / read-only `query`, `infra/neo4j/docker-compose.yml`. `graphdb selftest` against live Neo4j 2026.07.1 (Docker, macOS): 14/14 passed, 2026-11-04
- Audit chain: events hash-chained with the Switch `chat_message_id` inside each hash; `ledger verify` checks it (`tests/test_audit_chain.py`)
- Closes ("locks"): boundary + factor set locked per close, phase in the ledger, versions; approvals, gap closes and publish need the room's `chat_message_id` (`tests/test_publish_needs_room.py`)
- Model adapter: extract + phrase only (phrase can't change a fact), token budget per agent per close (warn 80%, stop 100%), replay mode
- `carbonroom/core.py` (core API seam; P2 slots via `@core.implements`) and the `@collector` agent (room event in, ops out; checkable "all collected" report; "why didn't you consider X?"; never marks VERIFIED)
- LLM: `nvidia/nemotron-3-ultra-550b-a55b`, bench 13/13 exact (backup `nvidia/nemotron-3.5-bolt-e4b`, also 13/13); seed extractions re-saved with it

**Next**
- PR #1 merged. PR #2 landed on `feat/ingest` instead of `main` (stacked base): retarget #3, #4 and the knowledge-graph PR to `main` and merge in order
- Help Richa move her branch onto `main` and `carbonroom.ledger.db` (her branch has no shared history and uses a stand-in `carbonroom/db.py`)
- Possible next (asked, not started): collector explains its decisions ('why didn't you consider X?'); evidence tags like [S-014]; check typed numbers against bills
- Team sign-off on `contracts/CHANGES.md`
- Stretch, only after everything else works: Drive/email connectors using fictional files only

**Blocked**
- Nothing.

## Richa (Calculation, Checker & Report)

## Akshar (Switch Room, Demo & Submission)
