# P2 handoff: calculation, checks, resolution, reporting

Owner: Richa. Package: `carbon_room.calc`. Everything here is reached through `carbon_room.core`; P3 never imports the ledger.

## What P2 provides now

| Function | Behaviour |
|---|---|
| `core.calculate(close_id)` | Prices every live claim, including prior-month baselines and both data-centre bases. An unchanged rerun writes no events. |
| `core.check(close_id)` | Applies R1–R7, merges the missing Warehouse source into its period-gap thread, records actionable gaps and verifies only eligible claims. An unchanged rerun writes no events. |
| `core.resolve(gap_id, action, actor, chat_message_id, payload)` | Applies a configured human option, records the room-linked decision and reruns calculate/check. |
| `core.summary(close_id)` | Read-only verified/excluded totals, coverage, source coverage, open gaps and data-centre line. |
| `core.draft_report(close_id)` | Versioned report with S-tags, conflict decisions, exclusions and review flags; sets DRAFTED. |
| `core.trace(close_id, tag)` | Recomputes a tagged calculation from the stored claim, source, factor and approvals. |
| `core.publish(close_id, actor, chat_message_id)` | Human lead gate; writes JSON, Markdown, PDF and offline HTML under `out/<month>/v<n>/`, then records publish approval and PUBLISHED. |
| `calc.calculator.compute / recompute` | Pure Decimal arithmetic. The formula string records every input. `recompute` reruns it from stored inputs and reports an exact match or not. |
| `calc.factors` | Loads `config/factors.csv`, resolves the locked factor per site and activity, resolves a vendor's own reference (`Ember 2024 IE`), and decides whether a factor is stale (`is_stale`). Malformed or catalogue-missing vendor references raise `FactorReferenceError`. |

## How a factor is chosen

1. A factor already on the claim is honoured only if `factors.ensure_allowed` accepts it: right activity, and the source and geography the site's config prescribes (`sites.yaml` grid, or `diesel_factor`). Otherwise `FactorNotAllowed` is raised. The version is not checked: an older edition is priced as it is, and rule R3 decides whether it is stale.
2. Otherwise the locked set pins the version for the site's source.
3. Every choice is saved with `set_factor` (actor `calculator`), so the audit log shows it.

## Calculation bases

- Electricity is `location`. Diesel has no basis.
- A data-centre claim receives **location-based** (IT kWh × PUE × grid factor) and, when supplied, **market-based** (vendor-reported kgCO2e) calculations. Both persist; only location enters the close total. Each verified calculation, including market, gets an S-tag. A zero market figure is disclosed as certificate-based, not a zero location footprint.

## P1 contract in use

- `latest_calculation(conn, claim_id, basis=...)` and `live_calculations(conn, claim_id)` are merged and used. P2 passes an explicit `location` basis for customer-facing data-centre totals.
- Source-tag lookup uses the persisted calculation id so a later supersession cannot silently change an already tagged row.

## For P3

- `calculate` is internal to a close; the room normally calls `check` and `resolve`, which run it. Do not call those after PUBLISHED; start a new close version instead.
- P3 must derive `Actor` and `chat_message_id` from authenticated Switch events, not from message text. The P2 human actions still trust that P3 boundary.
- `publish` allows open gaps but excludes those claims and lists each gap/owner in the output.
- A `FactorNotAllowed` or `FactorNotFound` means config or data is wrong, not that a person did something wrong; show it as a system error.

## Decisions on record

- **eGRID:** the locked set pins eGRID2023 Rev 2, the newest edition EPA has published. There is no eGRID2024.
- **Age rule:** a factor older than `rules.stale_max_age_months` is stale unless it is the latest published edition (`latest_published` in `config/carbon_room.yaml`).
- **Stale-factor trap size:** with the real Ember figures the 2024 vs 2025 difference is tiny (0.69 kgCO2e). The rule fires on the version mismatch.
- **Extraction mode:** `llm.mode` stays `rules`; `replay` would fail ingestion until the replay cache is populated.

## Known boundaries

- The F6 PDF is included as `report.pdf`; it is rendered offline from the same ledger snapshot as Markdown, JSON and coverage HTML.
- The offline acceptance suite uses deterministic `rules` extraction and also checks `replay` with temporary test-generated cache entries. The P1 runtime replay cache is not shipped with the seed; switching `llm.mode` to `replay` without generating that cache fails closed.
- `data/seed/EXPECTED.md` is generated from a temporary end-to-end ledger. `python -m scripts.generate_expected --check` detects drift in the seeded calculation and resolution outcome.
- A human can publish a truthful incomplete close; the report labels unverified rows, coverage and open gaps rather than inventing a complete total.
- P1 collection and ledger mutations reject a PUBLISHED close. P3 should start a new close version for later evidence; P2 calculate/check/resolve also reject post-publication edits.
- `core.resolve` resolves an open gap on the latest close. Gap IDs such as `G-1` repeat across versions; P3 must keep its existing old-thread guard before calling it. An upload is checked against its gap's site/month/activity before the source and claim are committed.
- Before publication, Watchdog re-evaluates a previously VERIFIED claim if new blocking evidence or a human rejection appears. The shared contract's immutable-VERIFIED sentence conflicts with its no-blocked-VERIFIED rule; the safety choice is logged for team approval in `contracts/CHANGES.md`.
