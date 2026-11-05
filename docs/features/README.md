# Feature docs: Ingestion & Ledger (Ujjwal)

One file per shipped feature. Each one says **why** the feature exists, **how it is designed**, the
**architecture** (diagram), the **decisions** behind it, a **code map**, and how it is **tested**.

| Feature | Doc | Main code |
| --- | --- | --- |
| Ledger (schema + access layer) | [ledger.md](ledger.md) | `contracts/schema.sql`, `carbonroom/ledger/db.py` |
| Seed data with demo traps | [seed-data.md](seed-data.md) | `carbonroom/ingest/seedgen.py`, `carbonroom/ingest/seed.py`, `data/seed/` |
| Ingestion (collect → extract with proof → consolidate) | [ingestion.md](ingestion.md) | `carbonroom/ingest/` |
| Model provider layer | [llm.md](llm.md) | `carbonroom/llm.py` |
| Background batch run (orchestrator / LangGraph) | [batch-run.md](batch-run.md) | `carbonroom/ingest/batch.py` |
| Contract-compatible shared types | [contract-compatibility.md](contract-compatibility.md) | `carbon_room/models.py` |
| Core API and the @collector agent | [core-and-collector.md](core-and-collector.md) | `carbonroom/core.py`, `carbonroom/agents/collector.py` |
| Knowledge graph (lineage, impact, graph export; mirrored into Neo4j) | [knowledge-graph.md](knowledge-graph.md) | `carbonroom/ledger/graph.py`, `carbonroom/graphdb/` |

Plain-language walkthrough for judges' questions: [../EXPLAIN_ingestion.md](../EXPLAIN_ingestion.md).
API hand-off for teammates: [../HANDOFF.md](../HANDOFF.md). Decision log: [../DECISIONS.md](../DECISIONS.md).

## Rules for keeping docs true

1. **One pull request per feature.** The PR that changes the code also changes that feature's doc,
   `docs/DECISIONS.md` (one line per decision), and `docs/HANDOFF.md` if a teammate-facing API changed.
2. **Docs describe the code as it is, not as planned.** Plans go in `docs/STATUS.md` under "Next".
3. **`tests/test_docs.py` fails when docs and code disagree.** It checks that:
   - every public function in `carbonroom/ledger/db.py` is in the HANDOFF function table, and every function
     in that table exists
   - every status transition in the code is written in HANDOFF exactly as the code allows it
   - every `carbonroom ...` command and `--flag` written in these docs exists in the CLI, and every
     Ingestion & Ledger command and flag is documented here (each feature doc has a Commands table)
   - every environment variable the code reads is in `.env.example`, and every `CR_*`/`LLM_*` variable listed
     there is actually read
   - every file path, link, and dotted module/function name (like `carbonroom.ledger.db.connect`) in these docs exists
   - every table in `contracts/schema.sql`, every gap kind and every document kind is listed in [ledger.md](ledger.md)
   - the extraction labels in the committed cache are the ones `THIRD_PARTY.md` and [seed-data.md](seed-data.md) name
   - the seed counts written in the docs ("11 documents, 10 activities") match a real `carbonroom seed`

   So if an AI (or a human) changes the code without the Markdown, `uv run pytest` goes red.
