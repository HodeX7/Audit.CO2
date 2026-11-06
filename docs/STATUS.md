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

This is an integration-ready P1 deliverable, not a claim that the complete P2/P3 Switch workflow has shipped.
P2 must add its contract-owned `config/carbon_room.yaml` factor-set catalog before P3 calls `start_close`.
P3 must supply authenticated Switch identity, replay protection, and authorization before it calls any P1 mutation;
that transport boundary is deliberately not implemented in this P1 branch.
