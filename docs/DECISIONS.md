# Decisions

One line each: decision, why, date. Newest at the bottom of each owner's section.

## Ujjwal (Ingestion & Ledger)

- Quantities, factors and results are stored as decimal strings (TEXT), never floats. Why: deterministic math, no float drift. 2026-11-03
- Honesty rules are enforced by SQLite triggers (no DELETE anywhere, immutable evidence, append-only events/approvals/calculations, gap close needs a human, period close needs a recorded APPROVE). Why: they hold even if an agent writes raw SQL. 2026-11-03
- The stored excerpt is the full source line(s) from the document, and the locator (page/line) is computed by code. The proposer's page number is only a search hint. Why: the evidence is the document's own words, not the model's paraphrase. 2026-11-03
- A claim is accepted only if its number AND unit appear in its excerpt; site and period each need their own excerpt (exactly one known site; exactly one month). Excerpts shorter than 8 characters are refused. Why: blocks an excerpt that exists but proves something else. 2026-11-03
- Proposer order in `auto` mode: cache → LLM (if a key is set) → rules. The rules proposer exists so judges can reproduce the demo with no key, and as a fallback on rate limits. Both go through the same verifier. 2026-11-03
- The committed seed cache was produced by the rules proposer and is labelled `rules-v1`. With an NVIDIA key, `carbonroom seed --refresh-cache --proposer llm` regenerates it with the LLM (labelled `llm:nvidia:<model>`). Why: no key was available while building; we label honestly. 2026-11-03
- Default NVIDIA model `meta/llama-3.3-70b-instruct`, provisional until `carbonroom llm bench --models a,b,c` is run with a key. Candidates: `meta/llama-3.3-70b-instruct`, `nvidia/nemotron-3-super-120b-a12b`, `deepseek-ai/deepseek-v3.1` (all listed for the NVIDIA API in public docs). 2026-11-03
- NVIDIA calls: temperature 0, throttled to `CR_LLM_RPM`=35/min (free tier is about 40), retries on 429/5xx/timeouts honouring Retry-After, max 5 attempts. Anthropic calls send no temperature or response_format (its OpenAI-compat layer rejects them on recent models). 2026-11-03
- Anthropic base URL override is `CR_ANTHROPIC_BASE_URL`, not `ANTHROPIC_BASE_URL`. Why: Claude Code may set the latter on our machines. 2026-11-03
- A corrected document ("Replaces bill: X", proven by an excerpt) marks X's document `superseded_by` and records `replaces_activity_ids` on the new row. Ingestion does NOT change the old row's status. Why: the checker owns decisions, and this is what makes the "false done" reopen visible. 2026-11-03
- Two documents claiming the same thing (INV-204 vs INV-204B) are both stored; ingestion opens no conflict gap. Why: honesty rule 2 (never pick one silently); detection is the checker's job. 2026-11-03
- The cloud provider is a `sites` row with `kind='cloud'` (owner Dev, room `cr-cloud`, grid SRVC for us-east-va). Why: its gaps route like any site's; Scope 3 Cat 1 stays separate in the report. 2026-11-03
- New table `expected_documents`; diesel is `as_delivered`, so months without a delivery are not "missing". Why: missing-bill detection without guessing. 2026-11-03
- Seed files are referenced in place; every other upload is copied to `data/store/<sha256><ext>` (gitignored). Why: evidence can't change or disappear after it is recorded. 2026-11-03
- Units: MWh→kWh ×1000, Dth/MMBtu→therms ×10, litres→US gallons ÷3.785411784 (exact definition), rounded to 0.001 gal. Gas volume units (ccf, m³) are refused, because they need the utility's heat content. 2026-11-03
- Hand-off with Akshar: synchronous `carbonroom ingest <file> --from --room --thread --message --gap --json` (recommended), or the `data/inbox/<room>/` watch folder with a `.meta.json` sidecar. 2026-11-03
- CLI plugin hook: teammates add commands in `carbonroom/{calc,check,report,switchbridge}/cli.py` via `register(subparsers)`, so nobody edits `cli.py` and merges stay clean. 2026-11-03
- Seed PDFs are generated with reportlab `invariant` mode, so the bytes and hashes are reproducible and cache keys stay valid. 2026-11-03
- `carbonroom seed` resets by removing the database file, not with SQL DELETE. 2026-11-03
- September 2026 is loaded `OPEN`/`UNVERIFIED`, like October. Ingestion never verifies or closes a period. 2026-11-03

## Richa (Calculation, Checker & Report)

## Akshar (Switch Room, Demo & Submission)
