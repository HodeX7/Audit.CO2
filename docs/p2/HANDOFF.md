# P2 handoff: calculation (what exists today)

Owner: Richa. Package: `carbon_room.calc`. Everything here is reached through `carbon_room.core`; P3 never imports the ledger.

## What P2 provides now

| Function | Behaviour |
|---|---|
| `core.calculate(close_id)` | Prices every live **non-data-centre** claim of the close, both months (the prior month is the baseline for later rules). Returns the live calculations. Safe to re-run: unchanged claims get no new calculation and no event. |
| `calc.calculator.compute / recompute` | Pure Decimal arithmetic. The formula string records every input. `recompute` reruns it from stored inputs and reports an exact match or not. |
| `calc.factors` | Loads `config/factors.csv`, resolves the locked factor per site and activity, resolves a vendor's own reference (`Ember 2024 IE`), and decides whether a factor is stale (`is_stale`). Malformed or catalogue-missing vendor references raise `FactorReferenceError`. |

## How a factor is chosen

1. A factor already on the claim is honoured only if `factors.ensure_allowed` accepts it: right activity, and the source and geography the site's config prescribes (`sites.yaml` grid, or `diesel_factor`). Otherwise `FactorNotAllowed` is raised. The version is not checked: an older edition is priced as it is, and rule R3 decides whether it is stale.
2. Otherwise the locked set pins the version for the site's source.
3. Every choice is saved with `set_factor` (actor `calculator`), so the audit log shows it.

## Calculation bases

- Electricity is `location`. Diesel has no basis.
- The data-centre line needs two records per claim: **location-based** (IT kWh × PUE × grid factor) and **market-based** (the vendor's reported figure, `basis="market"`). That requires the ledger to supersede per basis. `p1-contract-compliance` already does this; `main` does not yet. The data-centre calculation therefore lands after that P1 branch merges.
- Until then `calculate` **skips** data-centre claims and logs a warning naming each one. They have no calculation, so they cannot be VERIFIED.

## For Ujjwal (P1)

- Please expose the per-basis reads publicly once your branch is merged: `latest_calculation(conn, claim_id, basis=...)` and `live_calculations(conn, claim_id)`. P2 needs one record per basis and will not read the table directly.
- With no basis given, `latest_calculation` should keep preferring the location (or basisless) record, so no total ever silently uses the market figure.

## For P3

- `calculate` is internal to a close; the room normally calls `check` and `resolve`, which run it.
- A `FactorNotAllowed` or `FactorNotFound` means config or data is wrong, not that a person did something wrong; show it as a system error.

## Decisions on record

- **eGRID:** the locked set pins eGRID2023 Rev 2, the newest edition EPA has published. There is no eGRID2024.
- **Age rule:** a factor older than `rules.stale_max_age_months` is stale unless it is the latest published edition (`latest_published` in `config/carbon_room.yaml`).
- **Stale-factor trap size:** with the real Ember figures the 2024 vs 2025 difference is tiny (0.69 kgCO2e). The rule fires on the version mismatch.
- **Extraction mode:** `llm.mode` stays `rules`; `replay` would fail ingestion until the replay cache is populated.

## Not built yet

Data-centre calculation, rules R1 to R6, `check`, `resolve`, `summary`, `draft_report`, `publish`, `trace`, compliance flags, and the trap tests. Each arrives as its own PR; this file is updated with each.
