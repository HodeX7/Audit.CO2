# P1 handoff: ingestion and ledger

Owner: Ujjwal. Package: `carbon_room`.

## What P1 guarantees

- SQLite is the authoritative ledger; quantities are stored as exact Decimal-compatible text.
- Source bytes are content-addressed and each source SHA-256 is unique within a close.
- Newly ingested claims are always `UNVERIFIED`.
- A parsed billing period determines a claim's month, including prior-period evidence collected for comparison.
- Diesel activity is recorded as Scope 1; electricity as Scope 2; cloud data-centre activity as `DC`.
- Missing, malformed, or reversed billing periods are retained as failed sources and create no claim.
- A claim must reference a successfully extracted source using its stored SHA-256, a verbatim excerpt containing its
  value, and the activity's required unit and scope. A selected factor must match the claim activity.
- Location-based and market-based calculations for a claim coexist; only a newer calculation with the same basis
  supersedes its predecessor.
- Audit events are hash chained and append-only.
- Standalone audit writes reserve a SQLite writer transaction before selecting their predecessor hash; sequential P1
  identifiers use the same reservation so concurrent writers cannot reuse an ID.
- Human uploads and every human-facing P1 ledger mutation require a real Switch `chat_message_id`; human actors
  cannot advance a close phase directly.
- Only the Watchdog/system identity can mark a claim `VERIFIED`.
- Source ingestion is idempotent by close and source hash.
- An upload's source, claims, and `room_file_ingested` audit event commit together; failed room-event recording
  rolls all three back and releases the source lease.

## Stable integration entry points

Use `carbon_room.core` rather than reaching into P1 implementation modules:

- P3 calls `ingest_file(close_id, path, actor, chat_message_id, site)` for an uploaded attachment.
- P3 uses `gap_for_thread`, `record_gap_thread`, and `resume_state` to restore room state.
- P2 uses `ledger` operations and contract dataclasses from `carbon_room.models`.
- P2/P3 must preserve `chat_message_id` when recording human actions.
- Before P3 starts a close, P2 must provide `config/carbon_room.yaml` with the allowed `factor_sets`; P1 rejects an
  unknown or unavailable factor set and records the selected one as `factor_set_locked`.
- Live model extraction can use the default Anthropic client or a vendor-neutral provider registered with
  `carbon_room.llm.set_completion_provider`; P1 validates extracted evidence deterministically either way.
- `tests/fixtures/emissions_reference/` is an offline P1 regression corpus. Its source metadata is test-only;
  P2 must not import it as production factors or use its national-grid references to calculate cloud allocations.
- P3 must construct `Actor` values from authenticated Switch events; P1 treats them as already authenticated input
  and cannot verify an arbitrary caller-provided identity. In particular, P3 must not trust a role, user id, or
  `chat_message_id` supplied in message text. It must enforce webhook verification, event replay protection, room and
  thread ownership, and authorization before invoking P1 mutations.
- P3 must pass a managed regular attachment file, not an arbitrary path or symlink. P1 rejects non-regular and
  symlinked files and limits an individual source to 10 MiB before parsing.

`claim_lock` is an internal P1 primitive. It must be entered on a connection without an active transaction so its
published lease is visible to competing SQLite workers; P2/P3 should use the public facade instead.

## Deliberate boundaries

P1 does not implement Switch transport, event authentication, Watchdog rules, calculation, reporting, or publish
logic. Those remain P2/P3 responsibilities. P2/P3 should not bypass the ledger or change the public `core`
function signatures without a documented cross-team contract change.

P2 must treat factor IDs as immutable versioned catalog rows: load them before a close starts and create a new factor
ID instead of overwriting a row referenced by a locked close; P1 rejects a changed repeat load. The current
close-scoped audit chain cannot represent
global factor-catalog bootstrap without a team-approved catalog-audit design.

## Verification before integration

`EXPECTED.md` is the deterministic P1 seed-ingestion acceptance baseline (nine claims, source-period assignment,
scope classification, idempotency, and audit verification).

```bash
uv run pytest
uv run ruff check .
uv run carbon-room --help
```
