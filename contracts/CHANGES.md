# Contract changes

Shared contracts change only with team agreement. Each entry: what, why, who, status.

## 2026-11-03 - schema.sql v1 (Ujjwal) - PROPOSED, needs Richa + Akshar approval

`contracts/schema.sql` implements every table and column in Section 5.3 exactly. These are
**additive** (no contract column was renamed or removed):

| Table | Added | Why |
| --- | --- | --- |
| all | `CHECK` constraints on status/kind/scope enums; a trigger on every table that aborts `DELETE` | Honesty rule 3 enforced by the database, not by goodwill |
| `sites` | `kind` (`facility`/`cloud`), `aliases_json` | Nimbus Cloud is a "site" row so gaps route to Dev in `cr-cloud`; aliases let code match a site named in a document |
| `source_docs` | `original_name`, `doc_ref`, `page_count`, `meta_json` | `doc_ref` (e.g. INV-204) links corrected bills; `meta_json` keeps the chat thread/message/gap ids of an upload |
| `activities` | `status_reason`, `created_at`; status adds nothing new (`SUPERSEDED` was already in 5.3's rules) | Why a status changed is shown in chat |
| `instruments` | `site_id`, `certificate_id`, `excerpt`, `excerpt_locator`, `excerpt_sha256`, `status`, `superseded_by`, `extra_json`, `created_by`, `updated_at` | A REC is evidence too: same proof (excerpt + hash) and same supersede rule as activities |
| `gaps` | `created_at`, `created_by`, `dedupe_key` (UNIQUE), `refs_json` | The same problem is never opened twice; gaps point at the rows/docs they are about |
| `events` | `detail_json` | Structured audit details |
| new `expected_documents` | `site_id`, `category`, `doc_kind`, `frequency` (`monthly`/`as_delivered`) | Lets the checker detect the missing Reno bill without guessing |
| new `schema_meta` | `schema_version` | Migrations |

Conventions written into the schema header:
- Quantities, factors and results are **decimal strings** (TEXT). Read them with `Decimal(...)`, never `float`.
- Timestamps are ISO-8601 UTC; periods are `YYYY-MM`.
- Guards: evidence columns are immutable; `events`, `approvals`, `calculations` are append-only; a gap
  can't be closed without `resolved_by` + `resolution`; a period can't be `CLOSED` without a recorded
  `APPROVE` by the same handle.

## 2026-11-04 - audit chain on `events` (Ujjwal) - PROPOSED, additive

| Table | Added | Why |
| --- | --- | --- |
| `events` | `chat_message_id`, `prev_event_hash`, `event_hash`; trigger `events_hash_chain` | The architecture's "Audit chain: append-only, hashed" and its Event contract (`chat_message_id`, `prev_hash`, `hash`). Same hash column names as Richa's stand-in `carbonroom/db.py`. `event_hash` = sha256 of `[prev_event_hash or "", at, actor, action, ref or "", chat_message_id or "", detail_json]` as compact JSON. Older ledgers are hashed once by `migrate`. |

## 2026-11-04 - closes + the room gate (Ujjwal) - PROPOSED, additive

Implements the architecture's "Close" contract and "Switch is load-bearing" rule in the ledger.

| Table | Added | Why |
| --- | --- | --- |
| new `closes` | `id`, `period_id`, `version`, `sites_json`, `factor_set`, `phase`, `started_by`, `started_message_id`, `started_at`, `published_by`, `published_message_id`, `published_at`, `report_sha256` | The "locks" in Ledger + graph: boundary and factor set locked per close; the phase survives a crash; versions for corrections |
| `approvals` | `chat_message_id` (required by trigger) | Every human approval comes from the room |
| `gaps` | `finding_id`, `resolved_message_id` (required to close) | Gap contract fields; a gap closes only from a reply in the room |
| triggers | `approvals_need_room`, `gaps_resolution_needs_room`, `closes_lock_is_frozen`, `closes_published_is_final`, `closes_one_open_per_month`, `closes_publish_needs_room`, `periods_factor_set_locked_by_close`, `no_delete_closes` | Enforced by the database, not by goodwill |
| views | close nodes; `for_period`, `covers`, `started_by`, `published_by` links (`graph_version` 2) | The close is in the knowledge graph |

Breaking for callers: `record_approval` and `resolve_gap` now need `chat_message_id` (Richa's approve/resolve
paths pass the Switch message id they were triggered by).

## 2026-11-04 - knowledge-graph views (Ujjwal) - PROPOSED, additive, read-only

Two views added to `contracts/schema.sql`: `ledger_edges(src_type, src_id, rel, dst_type, dst_id, detail)` and
`ledger_nodes(type, id, label, status, period_id)`. No table or column changes; nothing is stored twice. Gap
`refs_json` keys `activity_ids`, `activity_id`, `source_doc_id`, `instrument_id` become graph edges (please use
them when opening gaps). `schema_meta.graph_version` lets `migrate()` rebuild the views when they change.
Details: `docs/features/knowledge-graph.md`.

## Noted for Akshar (chat formats, 5.4)

The gap example says "Please drop the **September** electricity bill" for a `2026-10` gap. It should say
**October** (the missing Reno bill is October). No schema impact.
