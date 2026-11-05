# P1 handoff: ingestion and ledger

Owner: Ujjwal. Package: `carbon_room`.

## What P1 guarantees

- SQLite is the authoritative ledger; quantities are stored as exact Decimal-compatible text.
- Source bytes are content-addressed and each source SHA-256 is unique within a close.
- Newly ingested claims are always `UNVERIFIED`.
- Audit events are hash chained and append-only.
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
- Live model extraction can use the default Anthropic client or a vendor-neutral provider registered with
  `carbon_room.llm.set_completion_provider`; P1 validates extracted evidence deterministically either way.

`claim_lock` is an internal P1 primitive. It must be entered on a connection without an active transaction so its
published lease is visible to competing SQLite workers; P2/P3 should use the public facade instead.

## Deliberate boundaries

P1 does not implement Switch transport, event authentication, Watchdog rules, calculation, reporting, or publish
logic. Those remain P2/P3 responsibilities. P2/P3 should not bypass the ledger or change the public `core`
function signatures without a documented cross-team contract change.

P2 must treat factor IDs as immutable versioned catalog rows: load them before a close starts and create a new factor
ID instead of overwriting a row referenced by a locked close. The current close-scoped audit chain cannot represent
global factor-catalog bootstrap without a team-approved catalog-audit design.

## Verification before integration

```bash
uv run pytest
uv run ruff check .
uv run carbon-room --help
```
