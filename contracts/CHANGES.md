# Contract changes

The active contract implementation lives in `carbon_room/`.

## 2026-11-07 — Verified-status safety clarification

- The team lead selected the safety invariant: a claim may be demoted from VERIFIED before publication if a new blocking finding or human rejection appears. Every status change is audited. A PUBLISHED close and its report remain immutable; later evidence starts a new close version. This reconciles the prior contradictory sentences in `00-CONTRACTS.md` without changing the frozen facade or SQLite schema.

## 2026-11-06 — P2 safety clarification for team review

- No frozen API signature or SQLite schema changes. A publish decision writes an explicit `report_published` audit
  event with the close version, Switch message id and timestamp; the existing `published_*` close fields remain.
- Internal hardening: gap uploads reject a wrong site/month/activity before P1 commits evidence; repeated `G-1` style
  identifiers are scoped to the latest close by `core.resolve`; source blobs are verified and atomically written;
  report files are staged before publication. These do not change the frozen facade signatures or schema.
- The contradictory VERIFIED wording was resolved in the 2026-11-07 clarification above.

## 2026-11-06 — P2 calculation-read handoff

- `ledger.latest_calculation(conn, claim_id, basis=...)` is now a public basis-filtered read. The permitted basis
  values are `"location"`, `"market"`, and legacy `None`; invalid values are rejected.
- `ledger.live_calculations(conn, claim_id)` returns every non-superseded calculation for a claim. When no basis is
  provided, `latest_calculation` prefers location, then legacy basisless, then market records to prevent a legacy
  caller from silently treating a market result as the location result.
- Calculations retain one live row per claim and basis. This confirms the existing write rule: a newer location
  calculation supersedes only location, and a newer market calculation supersedes only market.
- No SQLite migration is required: the existing `basis`, `created_at`, and `superseded_by` columns already express
  this contract.

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
  versioned factor rows before starting a close. P1 now rejects an attempt to change an existing factor id; repeat
  loads of an identical row are safe. P2 must create a new factor id for a changed factor.
- P1 readers reject symlinked, non-regular, or over-10 MiB source files before parsing. P3 must resolve a Switch
  attachment into a managed upload directory before calling P1; an arbitrary filesystem path is not a valid room
  attachment contract.
  A catalog-provenance/audit design needs team approval because the close-scoped `events` table cannot honestly
  represent a factor load performed before any close exists.
- No public `carbon_room.core` signature changed.

Schema initialization can add missing triggers to an existing database, but it cannot retrofit SQLite table
constraints or unique columns. Recreate a disposable local demo database before relying on the new constraints;
production migration ownership must be agreed with the integration lead.
