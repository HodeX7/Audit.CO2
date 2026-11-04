# Seed data: Brightwell Manufacturing (fictional)

**Everything here is invented** for the Carbon Room hackathon demo: Brightwell Manufacturing, its
sites and people, the utilities (Cedar Mesa Power & Light, Sagebrush Valley Electric, Pecan Hollow
Gas Company), the fuel suppliers (Northbank Energy Logistics, Redtail Fuel Supply), Nimbus Cloud, the
Cascadia Renewable Certificate Registry, every address, account and number. Each PDF page carries a
"FICTIONAL DOCUMENT" footer. No real bills or personal data are used.

## What's here

| Path | What |
| --- | --- |
| `sites.json` | Sites, owners, rooms, eGRID subregion labels, and which documents each site is expected to send |
| `docs/` | Loaded by `carbonroom seed` |
| `later/` | **Held back** for the live demo (uploaded in a gap thread) |
| `manifest.json` | One entry per document: folder, sender, room, traps (generated) |
| `extractions/<sha256>.json` | Cached extraction proposals, so the demo runs with no API key. Each one is still verified against the PDF on every run. |

Rebuild the PDFs with `carbonroom seed --regenerate-docs` (deterministic: same bytes, same hashes,
with the pinned reportlab version).

## Sites and people

| Site | Kind | eGRID subregion | Owner (handle) | Room |
| --- | --- | --- | --- | --- |
| Austin Plant (TX) | facility | ERCT | Omar (`omar`) | `cr-site-austin` |
| Reno Office (NV) | facility | NWPP | Lena (`lena`) | `cr-site-reno` |
| Nimbus Cloud (us-east-va) | cloud: Scope 3 Cat 1, reported separately | SRVC | Dev (`dev`) | `cr-cloud` |

Also: Maya (sustainability lead, runs the close) and Grace (controller, the approver).

## Documents and the traps they trigger

| File | Folder | Says | Trap (contract 5.6) |
| --- | --- | --- | --- |
| `2026-09_austin_electricity_ELB-AUS-2609.pdf` | docs | 182,400 kWh | baseline |
| `2026-10_austin_electricity_ELB-AUS-2610.pdf` | docs | 191,300 kWh (estimated read) | **4 False done**: the original |
| `2026-10_austin_electricity_ELB-AUS-2610-C.pdf` | **later** | 196,800 kWh, "Replaces bill: ELB-AUS-2610" | **4 False done**: the corrected bill. Ingesting it marks the original document `superseded_by`; the checker reopens the VERIFIED row |
| `2026-09_reno_electricity_ELB-RNO-2609.pdf` | docs | 14.62 **MWh** | unit normalization (stored as 14,620 kWh) |
| `2026-10_reno_electricity_ELB-RNO-2610.pdf` | **later** | 15.08 MWh | **1 Missing bill**: not loaded; Lena uploads it in the gap thread |
| `2026-09_austin_gas_GAS-AUS-2609.pdf` | docs | 4,800 therms | baseline for the outlier |
| `2026-10_austin_gas_GAS-AUS-2610.pdf` | docs | 7,700 therms | **5 Outlier**: +60.4% vs September |
| `2026-09_austin_diesel_INV-188.pdf` | docs | 1,892.7 **L** (delivery DLV-7590) | unit normalization (stored as 499.998 US gal) |
| `2026-10_austin_diesel_INV-204.pdf` | docs | 500.0 gal, delivery **DLV-7731** | **2 Conflict** |
| `2026-10_austin_diesel_INV-204B.pdf` | docs | 550.0 gal, same delivery **DLV-7731** | **2 Conflict**: both rows are stored; the checker asks Omar "1 or 2" |
| `2026-09_nimbus_cloud_NC-2609.pdf` | docs | IT 36,900 kWh, PUE 1.36, WUE 0.43 L/kWh (page 2) | **6 Data-centre line** (baseline) |
| `2026-10_nimbus_cloud_NC-2610.pdf` | docs | IT 38,200 kWh, PUE 1.35, WUE 0.42 L/kWh (page 2) | **6 Data-centre line** |
| `2026-10_rec_REC-WECC-2023-55120.pdf` | docs | 120 MWh REC, WECC Northwest (Oregon), vintage 2023, claimed against Nimbus Cloud us-east-va for Oct 2026 | **6 REC quality**: wrong region (generated in the Northwest, claimed against a Virginia load) and stale vintage (2023 for 2026 use) |

**Trap 3, stale factor**, is not a document: it lives in Richa's factor sets (`data/factors/`). It fires
when a calculation uses an older factor edition than the period's locked `factor_set_version`.

## After `carbonroom seed`

11 documents, 10 activities (all `UNVERIFIED`), 1 REC instrument, 0 gaps.
`carbonroom ledger show --period 2026-10` lists them, plus "Expected but missing: Reno Office electricity".

## Live demo moments

```bash
# Lena answers the missing-bill gap in cr-site-reno
carbonroom ingest data/seed/later/2026-10_reno_electricity_ELB-RNO-2610.pdf --from lena --room cr-site-reno --gap GAP-012 --json

# The utility re-issues Austin's October bill (after the checker VERIFIED the original)
carbonroom ingest data/seed/later/2026-10_austin_electricity_ELB-AUS-2610-C.pdf --from omar --room cr-site-austin --json
```
