# Status — Richa (Person 2: Calculation, Checker & Report)

Last updated: 2026-11-04

## Done

- `data/factors/v1-2026-10.csv` + `v0-stale.csv` — locked factor set, real sourced values
  (EPA, eGRID, Green-e), citations in `THIRD_PARTY.md`.
- `carbonroom/calc/` — deterministic Calculator (Scope 1, Scope 2 location+market, data-centre
  line with PUE/WUE, REC allocation that doesn't double-count a certificate). 15 unit tests.
- `carbonroom/check/` — Checker/Watchdog, all 6 checks (missing/conflict/stale/outlier/
  false-done/REC quality), idempotent, plus human-resolution parsing. 16 unit tests.
- `carbonroom/report/` — Reporter (VERIFIED-only totals, coverage %, data-centre line, approval
  gate that hard-refuses an unapproved or stale-approved publish) + `ask` (UNKNOWN + gap owner
  when only unverified data exists). 16 unit tests.
- `contracts/report.schema.json` — drafted, matches brief Section 5.5 exactly.
- `carbonroom/db.py` + `carbonroom/seed_demo.py` — placeholder SQLite layer implementing the
  shared `contracts/schema.sql` as-is, with demo data modeling all 6 traps, so this part runs
  end to end without waiting on Person 1's real ingestion.
- `carbonroom/cli.py` — `seed-demo | calc | check | resolve | report | approve | ask`. 6
  CLI-level tests (run as real subprocesses against a real temp SQLite db).
- Ran the full workflow for real, by hand, start to finish (see `docs/EXPLAIN_calc.md` for the
  two real bugs this caught: REC double-counting, and SQLite silently turning a stored Decimal
  back into a float).
- `docs/EXPLAIN_calc.md`, `THIRD_PARTY.md` written.
- 53/53 tests passing (`python3 -m unittest discover -s tests`).

## Next

- Swap `carbonroom/seed_demo.py` for Person 1's real Collector/Consolidator output, once it
  exists — no changes needed to `calc`/`check`/`report`/`cli.py` themselves, since they only
  read/write the shared schema.
- Hand the report JSON shape + exact gap-post text + CLI command list to Akshar for the Switch
  room wiring (see `docs/HANDOFF.md`).
- Decide with the team on the `id` naming scheme for factors (currently `ef-elec-erct-loc-v1`
  style) if anything else references a factor by name.
- Confirm Nimbus Cloud's actual data-centre grid region with whoever seeds the real cloud
  invoice data (currently assumed ERCT for the demo).
- `mom_change_pct` in the Reporter needs the prior period's totals passed in explicitly — the
  CLI doesn't currently wire that up (always `None` for now). Low priority; not required for
  the core demo traps.

## Blocked on

- Nothing blocking right now. Working entirely against the shared `contracts/schema.sql` with
  placeholder seed data until Person 1's real activities are flowing into the same tables.

## Local git state (as of now)

Working in a local clone of `HodeX7/Audit.CO2`, **not yet committed or pushed** — repo is still
empty on `main` (no teammate has pushed yet either), and the team hasn't decided on commit/push
timing. All of the above exists only in this local checkout for now.
