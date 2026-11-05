# Decisions

## Ujjwal — P1 Ingestion & Ledger

- `carbon_room` is the only runtime package. Why: Richa and Akshar had not imported the legacy package, so removing
  it now eliminates duplicate APIs and schemas before integration begins. 2026-11-05
- SQLite remains authoritative; quantities and factors are Decimal text. Why: reproducible calculations and audit
  evidence must not drift through floating point. 2026-11-05
- P1 validates close phases and claim statuses in code and in fresh SQLite schemas. Why: callers receive clear
  contract errors and new ledgers cannot persist invalid state. 2026-11-05
- Audit events are append-only at the SQLite layer. Why: hash verification detects tampering, while database
  triggers prevent accidental in-place rewrites in normal application use. 2026-11-05
- P1's live extraction budget is charged through the caller's ledger connection. Why: a close must never be charged
  against an unrelated default database during tests, demos, or worker execution. 2026-11-05
- Ingestion reserves a source SHA-256 with `BEGIN IMMEDIATE` before allocating a source id. The lease is published
  before source writes, so a competing worker can read it in WAL mode and receive `LockHeld` rather than a database
  lock error. `claim_lock` owns that transaction boundary; callers must enter it with no active transaction.
  2026-11-05
- Public emissions publications are represented only as pinned provenance beside fictional P1 test evidence, never as
  a production factor catalog. Why: source edition, geography, boundary, scope, and allocation method must be
  selected and owned by P2 before any customer-facing calculation can be valid. 2026-11-05
- P1 readers reject symlinked, non-regular, and over-10 MiB sources before parsing. Why: ingestion must not follow a
  caller-controlled filesystem link or allow one attachment to consume unbounded local resources. P3 owns the
  managed Switch-attachment root and authenticated event boundary. 2026-11-05
