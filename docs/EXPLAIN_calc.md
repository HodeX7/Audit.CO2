# EXPLAIN: Calculation, Checker & Report (Richa, Person 2)

Plain-language walkthrough of this part, for answering judge questions without notes.

## What this part does, in one paragraph

Person 1's side produces raw ledger rows ("Austin used 48,200 kWh in October"), all starting
UNVERIFIED. This part turns those rows into trustworthy numbers (the **Calculator**), catches
anything missing/wrong/outdated before it can reach a report (the **Checker/Watchdog**), and
builds the final close pack from only the rows that survived that scrutiny (the **Reporter**).
Nothing in this part ever makes up a number, blends an estimate into a verified total, or
publishes anything without a human's explicit approval.

## The four files/folders, and why each exists

### `data/factors/*.csv` — the emission factors
A small table: "1 kWh of Texas electricity = 0.33413 kg CO2e." Every value is read from a real
published source (EPA, eGRID, Green-e — see `THIRD_PARTY.md`), never typed from memory. There
are two files: `v1-2026-10.csv` is the set locked for this close, and `v0-stale.csv` is a
deliberately outdated row we use to demonstrate the stale-factor trap.

### `carbonroom/calc/` — the Calculator
Plain code: `emissions = activity_quantity x factor`. No AI model ever does this arithmetic — an
LLM might extract "48,200 kWh" from a PDF (that's Person 1's job), but multiplying that by a
factor is deterministic Python using `Decimal`, so the same input always gives the exact same
output, and a judge could redo the multiplication by hand and get the same number.

Two judgment calls worth knowing:
- **Electricity always gets two numbers, side by side**: location-based (the grid's real average)
  and market-based (after subtracting any valid renewable certificates). We never show just one.
- **RECs (renewable certificates) are allocated once across a whole region/period**, not
  independently to every activity that happens to share that grid region — otherwise the same
  certificate could get "spent" twice. (`allocate_rec_coverage` in `calculator.py`.)

### `carbonroom/check/` — the Checker/Watchdog
Runs six checks over the ledger every time `carbonroom check` is called:
1. **Missing documents** — an expected site/month/category with no document at all.
2. **Conflicts** — two documents for the same delivery that disagree.
3. **Stale factor** — a calculation that used an older factor edition than this period's lock.
4. **Outlier** — a site's usage moved more than 40% versus last month.
5. **False-done** — a row marked VERIFIED whose source document has since been corrected/replaced.
   This is the "done is a claim, not a fact" check.
6. **REC quality** — a renewable certificate whose region or vintage doesn't actually match.

Every check only *proposes* gaps and status changes — it never fixes anything itself and never
sets a row to EXCLUDED or SUPERSEDED (only a human resolving a gap can do that). Running the
checker twice in a row never creates duplicate gaps (each gap has a stable `dedupe_key`).

### `carbonroom/report/` — the Reporter
Builds the final pack from **VERIFIED rows only**. Everything else is shown as a separate
"unverified, excluded" number — visible, but never blended into the headline total. The pack
isn't allowed to become `PUBLISHED` unless a real `APPROVE` decision exists whose hash matches
these *exact* numbers — if the numbers change after someone approves, that approval stops
counting. This is "Honesty Rule 1" (no one writes directly to the published total) enforced as
code, not just a policy.

Also in this folder: `ask.py` answers a plain question (e.g. "what's the Reno electricity
total?") only from VERIFIED rows — if the only matching data is unverified/missing/conflicting,
it answers **UNKNOWN** and names the gap and its owner, rather than guessing.

### `carbonroom/db.py` and `carbonroom/seed_demo.py` — the stand-in database
Person 1's real ingestion pipeline doesn't exist yet, so this is a small SQLite layer
implementing the exact shared schema (`contracts/schema.sql`), plus placeholder demo data
modeling all 6 traps above. Once real activities are flowing in from Person 1's Collector, this
file becomes unnecessary — nothing about `calc`/`check`/`report` needs to change, since they
only ever read/write the shared table shapes, never anything specific to this placeholder.

### `carbonroom/cli.py` — the commands
`carbonroom seed-demo | calc | check | resolve | report | approve | ask` — see
`docs/HANDOFF.md` for the exact command list Akshar's chat agents should call.

## The honesty rules, in code, not just policy

- **Rule 1** (no one writes the published total but a human-approved Reporter): `publish_report()`
  hard-refuses without a matching approval — tested in `tests/test_report.py`.
- **Rule 2** (never auto-resolve/auto-approve on silence): every status change in `check/` comes
  from either a deterministic rule or an explicit human reply in `resolve.py` — nothing times out
  into approval.
- **Rule 3** (never delete, only supersede): the Checker and Reporter never issue a SQL `DELETE`;
  a corrected document's `superseded_by` field points backward, and the old row stays.
- **Rule 4** (UNKNOWN when only unverified data exists): built into `ask.py` directly.

## Two real bugs we found by actually running this, not just unit testing

1. A single REC/PPA certificate was being counted as a full emissions offset against **two
   different activities** that happened to share one grid region — literally double-counting
   the same certificate. Fixed by allocating each certificate's volume once across everything
   that could claim it (`allocate_rec_coverage`).
2. SQLite's `REAL` column type silently turns a stored Decimal back into a `float` on read,
   which the Calculator's exact-arithmetic code rejects. Fixed by normalizing back to `Decimal`
   at the one boundary where rows leave the database (`db.get_factors`, `db.get_calculations`).

Neither showed up in isolated unit tests — both only appeared once we ran the real CLI against a
real database with more than one activity in play. Worth remembering before the demo: test the
actual multi-activity, multi-gap flow, not just each function alone.
