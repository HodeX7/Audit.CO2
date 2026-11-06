# Status

## Ujjwal — P1 Ingestion & Ledger

`carbon_room` is the sole runtime package. Its P1 contract ledger, source ingestion, audit chain, budget and lock
guards, seed data, room-message attribution helpers, graph trace, explain boundary, and developer CLI are
implemented and tested. P2 and P3 integrate through `carbon_room.core` and the frozen contract types.

The P1 test suite also contains a separate, offline, cited corpus of fictional UK and Ireland activities in
`tests/fixtures/emissions_reference/`. It verifies reader and ledger behavior without loading those references into
the production factor catalog.

This is an integration-ready P1 deliverable, not a claim that the complete P2/P3 Switch workflow has shipped.
P2 must add its contract-owned `config/carbon_room.yaml` factor-set catalog before P3 calls `start_close`.
P3 must supply authenticated Switch identity, replay protection, and authorization before it calls any P1 mutation;
that transport boundary is deliberately not implemented in this P1 branch.
