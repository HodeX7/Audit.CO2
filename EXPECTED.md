# Carbon Room P1 expected demo results

This file is the deterministic acceptance baseline for P1's synthetic seed corpus. It contains no customer data.

## Seed ingestion: October 2026 close

Create close `2026-10-v1` with sites `hq`, `warehouse-2`, and `dc-eu-west`, then run the P1 collector over
`data/seed/2026-09/` and `data/seed/2026-10/`.

| Expected result | Value |
| --- | --- |
| Sources seen | 9 |
| Claims created on first run | 9 |
| Claims created on repeat run | 0 (SHA-256 idempotency) |
| Claims with source period September 2026 | 5 |
| Claims with source period October 2026 | 4 |
| Diesel claims | Scope 1, unit `L` |
| Electricity claims | Scope 2, unit `kWh` |
| Cloud data-centre claims | Scope `DC`, unit `kWh` |
| Initial claim status | `UNVERIFIED` |
| Audit verification | `verify_audit(close_id).ok` is `True` |

The Warehouse-2 file stored in the October seed directory intentionally prints a September billing period. P1 must
retain **September** as the claim month because the evidence, not its storage folder or the active close, determines
the accounting period. P2 should use that prior-period claim for its variance comparison.

P1 ends at an auditable, unverified ledger. Calculation totals, findings, approval, publication, and the room
workflow remain P2/P3 responsibilities.
