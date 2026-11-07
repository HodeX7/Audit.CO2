# Status

## Ujjwal — P1 Ingestion & Ledger

`carbon_room` is the sole runtime package. Its P1 contract ledger, source ingestion, audit chain, budget and lock
guards, seed data, room-message attribution helpers, graph trace, explain boundary, and developer CLI are
implemented and tested. P2 and P3 integrate through `carbon_room.core` and the frozen contract types.

The P1 acceptance baseline in `EXPECTED.md` documents the nine-claim seed run. It preserves evidence billing
months (including comparison-period inputs), classifies diesel as Scope 1, and requires an intact audit chain.
The ledger additionally rejects fabricated source evidence, invalid calendar periods, cross-close claim replacement,
and activity-incompatible factor assignment; concurrency tests cover audit appends and identifier allocation.
Its calculation handoff now exposes basis-filtered reads and both live calculations per claim, so P2 can retain
location- and market-based data-centre results without overwriting either one.

The P1 test suite also contains a separate, offline, cited corpus of fictional UK and Ireland activities in
`tests/fixtures/emissions_reference/`. It verifies reader and ledger behavior without loading those references into
the production factor catalog.

The contract-owned `config/carbon_room.yaml` factor-set catalog is present. P3 owns authenticated Switch identity,
replay protection and room authorization before calling P1 mutations. The `make run` target now has a runner;
both real startup and the developer `init` command bootstrap the immutable factor rows into a fresh SQLite ledger.
Fake-Switch and real-core tests pass locally, but live Switch connectivity and human identity have not been
verified. No live room messages were sent as part of this worktree verification.

## Richa — P2 calculation, checks, resolution and reporting

On the isolated `p2-spec-completion` branch, F2–F6 required paths are implemented: Decimal calculation including
data-centre location/market bases; R1–R7 checks and tier-1 verification; room-attributed human gap options; read-only
summary; and source-tagged draft, trace, Markdown/JSON/HTML/PDF publication. F7 includes the October trap, renamed
March 2027 site, published-number recomputation, generated expected results, and temporary-cache replay suites.
Published closes reject P1 ledger mutations and uploads; subsequent evidence needs a new close version. P1/P3 schemas
and frozen signatures are unchanged. Production replay extraction remains unavailable until P1 cache entries are
populated. These changes require review and live Switch validation before merge.

## Akshar — P3 room and demo

The application now wires four WebSocket connections through one dispatcher to the P1/P2 core. `SwitchRoom`
routes posts, targeted hand-offs and board documents through each agent's operations client. An offline fake-Switch
test covers close-to-thread-resolution; real-core tests also cover all four fictional resolutions, publication
and audit verification both through direct handlers and through fake sockets. `README.md` and
`docs/setup-switch.md` explain setup, role mapping and fallbacks.
The wheel builds and imports in a separate temporary virtual environment with the real `uuid-utils` dependency.

Still manual and unverified: real Switch S1–S6 spikes, actual Lead/Priya sender ids in `config/people.yaml`, live
room startup, timed rehearsals, clean-machine run, video and submission. Do not claim live readiness from local
tests alone.
