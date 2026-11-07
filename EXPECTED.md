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

## P2 deterministic seed close (offline rules mode)

After calculation and the first Watchdog check, the five October source files yield four actionable threads: R2 HQ
diesel conflict, R3 stale Ireland data-centre factor, R4 Warehouse period mismatch with R1 missing evidence merged
into that thread, and R5 HQ electricity variance. The data-centre AI finding is informational. No blocked claim is
VERIFIED. A second unchanged calculation/check appends no audit events.

In the scripted resolution, the human picks the 2,400 L diesel invoice, selects the locked 2025 Ireland factor,
approves HQ variance, and uploads the held-back 18,500 kWh October Warehouse bill. The resulting current-month
location/basisless contributions are:

| Source pair | Verified kgCO2e |
| --- | ---: |
| HQ electricity, 48,300 kWh × 0.19503700802971 | 9420.28748783499300 |
| HQ diesel, 2,400 L × 2.58354 | 6200.49600 |
| Warehouse electricity, 18,500 kWh × 0.13096 | 2422.76000 |
| Ireland data-centre location, 12,000 kWh × PUE 1.2 × 0.270719 | 3898.3536000 |
| **Verified total** | **21941.89708783499300** |

The report total is **21.941897087834993 tCO2e**, with 4/4 source pairs and 100% emissions coverage after those
resolutions. The vendor's market-based data-centre value is 0 kgCO2e, shown and tagged separately; it never replaces
the location total. A published report traces every S-tag to a stored excerpt and exact recomputation. These numbers
are for synthetic fictional evidence, not a real emissions inventory.
