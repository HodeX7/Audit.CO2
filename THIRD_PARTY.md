# Third-party data and code

Everything below was pulled in for Person 2's part (Calculation, Checker & Report). Other
teammates should append their own sections for their parts.

## Emission factor data (public, government/nonprofit sources — cited per hackathon Rule 4)

| Source | Edition | Used for | License / terms |
|---|---|---|---|
| EPA GHG Emission Factors Hub | January 2025 edition | Natural gas, diesel CO2/CH4/N2O factors | US federal government work; public domain. |
| EPA eGRID | eGRID2023, rev. 2 (June 2025, 2023 generation data) | Electricity location-based CO2e by subregion (ERCT, NWPP) | US federal government work; public domain. |
| EPA eGRID | eGRID2022 (published Jan 2024, 2022 data) | Deliberately outdated factor, used only for the stale-factor demo trap | US federal government work; public domain. |
| Green-e Residual Mix Emissions Rates | 2025 edition (2023 data), released 2026-01-29, via Center for Resource Solutions (resource-solutions.org) | Electricity market-based (residual mix) CO2 by subregion | Published for public use in GHG accounting; attributed above. Values are CO2 only (table does not report CH4/N2O), noted explicitly in `data/factors/v1-2026-10.csv`. |
| GHG Protocol, "Global Warming Potential Values" (August 2024 table, citing IPCC AR6 WGI Ch. 7) | August 2024 | CH4 (fossil, 29.8) and N2O (273) 100-year GWP values, used to roll CH4/N2O into CO2e for Scope 1 fuels | Published by the GHG Protocol for public accounting use. |

Full source URLs are recorded as inline comments/citations in `data/factors/*.csv` and in
`docs/EXPLAIN_calc.md`. Every number was fetched from the primary source above (not a secondary
aggregator) during this hackathon's build window.

## Code dependencies

Only the Python standard library is used in `carbonroom/calc`, `carbonroom/check`,
`carbonroom/report`, `carbonroom/db.py`, and `carbonroom/cli.py` (no third-party packages):
`sqlite3`, `argparse`, `decimal`, `hashlib`, `json`, `csv`, `uuid`, `datetime`. This was a
deliberate choice to minimize setup risk for judges reproducing the demo — `python3` alone is
enough to run this part end to end.

Test suite: Python's built-in `unittest` (no pytest dependency), runnable with
`python3 -m unittest discover -s tests`.

## Reused vs. built during the hackathon (Rule 3)

Nothing in this part (`carbonroom/calc`, `carbonroom/check`, `carbonroom/report`,
`carbonroom/db.py`, `carbonroom/cli.py`, `carbonroom/seed_demo.py`, `data/factors/`,
`contracts/report.schema.json`) existed before this hackathon's build window (started Tue Nov 3,
10:31 AM PT). All of it was written during the event. The emission factor *values* above are
public third-party data, not reused code.
