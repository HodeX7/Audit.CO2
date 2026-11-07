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

## Richa — P2 calculation and close decisions

- Data-centre location and vendor market calculations coexist by basis. Only the location amount enters close totals;
  a certificate-based market zero is displayed separately and explicitly cautioned. Both bases receive S-tags when
  their claim is verified. 2026-11-06
- Watchdog gap identities are deterministic from rule, kind, site, month and claim ids. A mislabeled current-month
  source with a prior-month billing period opens one R4 thread that includes R1's missing-current-source consequence.
  Unchanged checks create no new events. 2026-11-06
- Human gap options require a P3-authenticated `Actor` and Switch message id. An R3 approval must select the offered
  locked factor; a generic approval cannot silently accept a stale factor. 2026-11-06
- Report coverage uses current-month live, calculated claims only. Verified totals exclude unverified values and use
  the data-centre location basis. Source coverage counts configured site/activity pairs, not file count. 2026-11-06
- Reporter Markdown/HTML templates use Python string formatting rather than Jinja2; PDF uses the existing ReportLab
  dependency. All outputs are offline views of one ledger snapshot with explicit gaps, source tags and review flags,
  not a legal finding. Published closes reject collection and ledger mutations; later evidence needs a new close
  version. 2026-11-07
- Gap uploads validate their expected site, month and activity before committing through P1's source lock. Close-local
  gap IDs are resolved against the latest close, matching P3's old-thread guard. Published files are staged before
  the final version-directory rename. Source storage refuses symlinks/oversized inputs, verifies existing SHA paths,
  and writes new blobs atomically. 2026-11-07

## Akshar — P3 Switch room runtime

- One process runs four agent WebSockets and one deduplicating dispatcher. Mutation handlers are serialized, while
  synchronous core operations run in a bounded thread pool so heartbeats stay live. The optional single-agent mode
  is explicit, never automatic. 2026-11-07
- Source-tree `uuid_utils` stubs were removed because they shadowed the installed dependency and returned UUID4
  where LangGraph expects UUID7. The built wheel already excludes the stubs; source and wheel now agree. 2026-11-07
- Offline fake-Switch and real-ledger tests are separate from the live deployment gate. `make run` may post in the
  configured room, so local verification does not execute it without a deliberate live-room check. 2026-11-07
