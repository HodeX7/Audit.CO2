# Decisions

## Ujjwal — P1 Ingestion & Ledger

- `carbon_room` is the only runtime package. Why: Richa and Akshar had not imported the legacy package, so removing
  it now eliminates duplicate APIs and schemas before integration begins. 2026-11-05
- SQLite remains authoritative; quantities and factors are Decimal text. Why: reproducible calculations and audit
  evidence must not drift through floating point. 2026-11-05
