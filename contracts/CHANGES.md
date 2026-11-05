# Contract changes

The active contract implementation lives in `carbon_room/`.

## 2026-11-05 — P1 integrity hardening

- Fresh ledgers enforce the published close-phase and claim-status literals with SQLite checks.
- Audit rows are append-only; updating or deleting an audit event is rejected by SQLite.
- `claim_lock` now publishes its lease in its own SQLite transaction and rejects connections with uncommitted work.
  This prevents an invisible lease during concurrent ingestion; P3 should call the public `core` functions rather
  than the internal lock directly.
- `start_close` now rejects an unknown or unavailable factor set and records the accepted set as
  `factor_set_locked`. P2 supplies the contract-owned factor-set catalog in `config/carbon_room.yaml`.
- A source with no proof-backed extraction candidate is retained as `FAILED`, with its deterministic rejection
  reason, rather than being reported as successfully extracted.
- A gap thread root message identifier is unique across the ledger.
- Gap primary identity is `(close_id, gap_id)`, so `G-1` correctly restarts for each close as specified in P1-2.5.
  **Integration note for P2/P3:** `core.resolve(gap_id, ...)` has no `close_id`, so their router must resolve the
  active close before looking up a repeated gap identifier. No P2/P3 implementation exists on this branch yet.
  The graph view represents this composite node as `<close_id>:<gap_id>` to keep graph edges unambiguous.
- Factor loading remains the fixed global-catalog API `load_factors(conn, rows)`. P2 must load immutable,
  versioned factor rows before starting a close and must not overwrite an existing factor id used by a close.
  A catalog-provenance/audit design needs team approval because the close-scoped `events` table cannot honestly
  represent a factor load performed before any close exists.
- No public `carbon_room.core` signature changed.

Schema initialization can add missing triggers to an existing database, but it cannot retrofit SQLite table
constraints or unique columns. Recreate a disposable local demo database before relying on the new constraints;
production migration ownership must be agreed with the integration lead.
