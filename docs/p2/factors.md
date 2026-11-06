# Factor catalogue (P2)

`config/factors.csv` is loaded into the ledger's `factors` table by `carbon_room.calc.factors.load`. Rows are immutable once a close has used them: change a value by adding a new `factor_id`.

Every value was read from the publisher's own file on 5 Nov 2026, not typed from memory. Two values were read by a research assistant instead of by us (marked below), so spot-check them before the demo.

| Factor id | Value | Unit | Where it came from | Checked how |
|---|---|---|---|---|
| `DEFRA-2026-UK-electricity_kwh` | 0.13096 | kgCO2e/kWh | DESNZ/DEFRA GHG Conversion Factors 2026, full-set workbook, sheet "UK electricity", row "Electricity generated / Electricity: UK / kWh / 2026". CO2 0.12943, CH4 0.00067, N2O 0.00086 | Read directly from the workbook |
| `DEFRA-2026-UK-diesel_l` | 2.58354 | kgCO2e/L | Same workbook, sheet "Fuels", Liquid fuels, "Diesel (average biofuel blend)", row "litres". CO2 2.55035, CH4 0.00029, N2O 0.0329 | Read directly from the workbook |
| `EGRID-2023-CAMX-electricity_kwh` | 0.19503700802971 | kgCO2e/kWh | EPA eGRID2023 Rev 2, "eGRID Subregion Total Output Emission Rates", CAMX CO2e = 429.983 lb/MWh | Web table read by a research assistant; the EPA summary-tables PDF, read directly, shows 430.0 for the same cell |
| `EMBER-2025-IE-dc_it_kwh` | 0.270719 | kgCO2e/kWh | Ember yearly electricity data (Europe), Ireland, 2025, Total generation: 270.719 gCO2e/kWh | Read by a research assistant; not re-read by us |
| `EMBER-2024-IE-dc_it_kwh` | 0.270767 | kgCO2e/kWh | Same file, 2024: 270.767 gCO2e/kWh | Read by a research assistant; not re-read by us |

## Conversions

- eGRID: 429.983 lb/MWh × 0.45359237 kg/lb ÷ 1000 kWh/MWh = 0.19503700802971 kgCO2e/kWh.
- Ember: gCO2e/kWh ÷ 1000.

## Things the team should know

1. **eGRID2024 does not exist.** EPA's pages (last updated Sept 2026) list only eGRID2023. The locked set therefore pins `EGRID: "2023"`, not 2024 as in the original brief. If EPA publishes eGRID2024 before submission, add a new row and change the set.
2. **The stale-factor trap is real but small in tonnes.** Ember's 2024 and 2025 figures for Ireland are 270.767 and 270.719 gCO2e/kWh. For the seeded 12,000 kWh at PUE 1.2 the difference is 0.69 kgCO2e. The rule fires on the version mismatch, not on the size of the difference, and the thread shows the real number. We do not alter a factor to make the demo look bigger.
3. **Two sources disagree for Ireland 2025.** Our World in Data's Ember-derived series shows 256.54 for 2025 against 270.719 in Ember's own file. We use Ember's file. Whether Ember's column is direct or lifecycle emissions is not stated in the file we read.
4. **DEFRA electricity is generation only.** Transmission and distribution losses are a separate sheet and are not Scope 2 location-based here.
5. **Earlier snippet of CAMX at 438.2 lb/MWh** appears in search results from before EPA's revisions. Rev 2 (June 2025) is the edition used.
