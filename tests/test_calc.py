"""Unit tests for carbonroom/calc, with hand-computed expected values.

Run with: python3 -m pytest tests/test_calc.py -v
(or: python3 -m unittest tests.test_calc -v, no pytest required)
"""

import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from carbonroom.calc import allocate_rec_coverage, calculate_activity, index_factors, load_factor_set

FACTORS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "factors"


def _index(csv_name: str) -> dict:
    return index_factors(load_factor_set(FACTORS_DIR / csv_name))


class TestScope1(unittest.TestCase):
    def setUp(self):
        self.idx = _index("v1-2026-10.csv")

    def test_natural_gas_mmbtu(self):
        # 120 mmBtu x 53.117 kg CO2e/mmBtu = 6374.04 kg
        activity = {
            "id": "act-ng-1", "category": "natural_gas",
            "quantity": "120", "unit": "mmbtu", "period_id": "2026-10",
        }
        calcs, issues = calculate_activity(activity, self.idx, region="US")[:2]
        self.assertEqual(issues, [])
        self.assertEqual(len(calcs), 1)
        self.assertEqual(calcs[0]["scope"], "1")
        self.assertEqual(calcs[0]["co2e_kg"], Decimal("120") * Decimal("53.117"))
        self.assertEqual(calcs[0]["co2e_kg"], Decimal("6374.040"))

    def test_natural_gas_therms_converts(self):
        # 1200 therms = 120 mmBtu -> same answer as above
        activity = {
            "id": "act-ng-2", "category": "natural_gas",
            "quantity": "1200", "unit": "therms", "period_id": "2026-10",
        }
        calcs, issues = calculate_activity(activity, self.idx, region="US")[:2]
        self.assertEqual(issues, [])
        self.assertEqual(calcs[0]["co2e_kg"], Decimal("6374.040"))

    def test_diesel_gallons(self):
        # 500 gallons x 10.244 kg CO2e/gallon = 5122.0 kg
        activity = {
            "id": "act-d-1", "category": "diesel",
            "quantity": "500", "unit": "gallon", "period_id": "2026-10",
        }
        calcs, issues = calculate_activity(activity, self.idx, region="US")[:2]
        self.assertEqual(issues, [])
        self.assertEqual(calcs[0]["scope"], "1")
        self.assertEqual(calcs[0]["co2e_kg"], Decimal("5122.000"))

    def test_unsupported_unit_raises_issue_not_guess(self):
        activity = {
            "id": "act-d-2", "category": "diesel",
            "quantity": "500", "unit": "litres", "period_id": "2026-10",
        }
        calcs, issues = calculate_activity(activity, self.idx, region="US")[:2]
        self.assertEqual(calcs, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "unsupported_unit")


class TestScope2Electricity(unittest.TestCase):
    def setUp(self):
        self.idx = _index("v1-2026-10.csv")

    def test_austin_location_and_market_no_rec(self):
        # 48,200 kWh in ERCT
        # location: 48200 x 0.33413 = 16105.066 kg
        # market (no REC): 48200 x 0.37368 = 18011.376 kg
        activity = {
            "id": "act-elec-1", "category": "electricity",
            "quantity": "48200", "unit": "kwh", "period_id": "2026-10",
        }
        calcs, issues, _ = calculate_activity(activity, self.idx, region="ERCT")
        self.assertEqual(issues, [])
        by_scope = {c["scope"]: c["co2e_kg"] for c in calcs}
        self.assertEqual(by_scope["2_location"], Decimal("16105.06600"))
        self.assertEqual(by_scope["2_market"], Decimal("18011.37600"))

    def test_austin_market_with_matching_rec_offsets_partially(self):
        # Same 48,200 kWh, but a 20 MWh REC matches region+period exactly.
        # 20 MWh = 20000 kWh covered at zero; remainder 28200 kWh x 0.37368
        # = 10,537.776 kg
        activity = {
            "id": "act-elec-2", "category": "electricity",
            "quantity": "48200", "unit": "kwh", "period_id": "2026-10",
        }
        instruments = [{
            "id": "rec-1", "period_id": "2026-10", "kind": "REC",
            "mwh": "20", "region": "ERCT", "vintage": "2026", "quality_flags": "ok",
        }]
        calcs, issues, _ = calculate_activity(activity, self.idx, region="ERCT", instruments=instruments)
        self.assertEqual(issues, [])
        by_scope = {c["scope"]: c["co2e_kg"] for c in calcs}
        self.assertEqual(by_scope["2_market"], Decimal("28200") * Decimal("0.37368"))
        self.assertEqual(by_scope["2_market"], Decimal("10537.77600"))

    def test_rec_wrong_region_does_not_offset(self):
        # A REC registered for NWPP must not reduce an ERCT activity's
        # market-based total -> same as the no-REC case.
        activity = {
            "id": "act-elec-3", "category": "electricity",
            "quantity": "48200", "unit": "kwh", "period_id": "2026-10",
        }
        instruments = [{
            "id": "rec-2", "period_id": "2026-10", "kind": "REC",
            "mwh": "20", "region": "NWPP", "vintage": "2026", "quality_flags": "ok",
        }]
        calcs, issues, _ = calculate_activity(activity, self.idx, region="ERCT", instruments=instruments)
        by_scope = {c["scope"]: c["co2e_kg"] for c in calcs}
        self.assertEqual(by_scope["2_market"], Decimal("18011.37600"))

    def test_flagged_rec_does_not_offset(self):
        # A REC the Checker already flagged (wrong vintage etc.) must not
        # silently offset anything -> same as the no-REC case.
        activity = {
            "id": "act-elec-4", "category": "electricity",
            "quantity": "48200", "unit": "kwh", "period_id": "2026-10",
        }
        instruments = [{
            "id": "rec-3", "period_id": "2026-10", "kind": "REC",
            "mwh": "20", "region": "ERCT", "vintage": "2019",
            "quality_flags": "vintage_mismatch",
        }]
        calcs, issues, _ = calculate_activity(activity, self.idx, region="ERCT", instruments=instruments)
        by_scope = {c["scope"]: c["co2e_kg"] for c in calcs}
        self.assertEqual(by_scope["2_market"], Decimal("18011.37600"))

    def test_reno_location_nwpp(self):
        # 10,000 kWh in NWPP: 10000 x 0.28815 = 2881.5 kg
        activity = {
            "id": "act-elec-5", "category": "electricity",
            "quantity": "10000", "unit": "kwh", "period_id": "2026-10",
        }
        calcs, issues, _ = calculate_activity(activity, self.idx, region="NWPP")
        by_scope = {c["scope"]: c["co2e_kg"] for c in calcs}
        self.assertEqual(by_scope["2_location"], Decimal("2881.50000"))


class TestCloudDataCentreLine(unittest.TestCase):
    def setUp(self):
        self.idx = _index("v1-2026-10.csv")

    def test_facility_kwh_and_water_from_it_kwh(self):
        # IT = 10,000 kWh, PUE = 1.4 -> facility = 14,000 kWh
        # location: 14000 x 0.33413 = 4677.82 kg
        # market (no REC): 14000 x 0.37368 = 5231.52 kg
        # water: IT kWh x WUE = 10000 x 0.5 = 5000 L  (NOT facility kWh)
        activity = {
            "id": "act-cloud-1", "category": "cloud_compute",
            "quantity": "10000", "unit": "kwh", "period_id": "2026-10",
            "extra_json": {"pue": "1.4", "wue": "0.5"},
        }
        calcs, issues, extras = calculate_activity(activity, self.idx, region="ERCT")
        self.assertEqual(issues, [])
        by_scope = {c["scope"]: c["co2e_kg"] for c in calcs}
        self.assertEqual(by_scope["dc_location"], Decimal("4677.82000"))
        self.assertEqual(by_scope["dc_market"], Decimal("5231.52000"))
        self.assertEqual(extras["facility_kwh"], Decimal("14000.0"))
        self.assertEqual(extras["water_l"], Decimal("5000.00"))

    def test_missing_pue_produces_issue_not_a_guess(self):
        # No PUE on the invoice -> Calculator refuses to assume PUE=1.
        activity = {
            "id": "act-cloud-2", "category": "cloud_compute",
            "quantity": "10000", "unit": "kwh", "period_id": "2026-10",
            "extra_json": {"wue": "0.5"},
        }
        calcs, issues, extras = calculate_activity(activity, self.idx, region="ERCT")
        self.assertEqual(calcs, [])
        codes = {i.code for i in issues}
        self.assertIn("missing_pue", codes)
        self.assertNotIn("facility_kwh", extras)
        self.assertEqual(extras["water_l"], Decimal("5000.00"))

    def test_missing_wue_still_computes_emissions(self):
        activity = {
            "id": "act-cloud-3", "category": "cloud_compute",
            "quantity": "10000", "unit": "kwh", "period_id": "2026-10",
            "extra_json": {"pue": "1.4"},
        }
        calcs, issues, extras = calculate_activity(activity, self.idx, region="ERCT")
        self.assertEqual(len(calcs), 2)
        codes = {i.code for i in issues}
        self.assertIn("missing_wue", codes)
        self.assertNotIn("water_l", extras)


class TestRecAllocationIsNotDoubleCounted(unittest.TestCase):
    """Regression test for a real bug found during a live dry run: two
    activities sharing one region/period each independently 'saw' the
    full REC and both got its full offset -- double-counting the same
    3 MWh. allocate_rec_coverage must split one pool across both."""

    def setUp(self):
        self.idx = _index("v1-2026-10.csv")
        self.region_by_site = {"austin": "ERCT", "cloud": "ERCT"}
        self.instruments = [{
            "id": "rec-1", "period_id": "2026-10", "kind": "REC",
            "mwh": "3", "region": "ERCT", "vintage": "2026", "quality_flags": "ok",
        }]
        self.activities = [
            {"id": "act-elec-austin", "site_id": "austin", "category": "electricity",
             "quantity": "48200", "unit": "kwh", "period_id": "2026-10"},
            {"id": "act-cloud", "site_id": "cloud", "category": "cloud_compute",
             "quantity": "6000", "unit": "kwh", "period_id": "2026-10",
             "extra_json": {"pue": "1.3", "wue": "0.5"}},
        ]

    def test_without_allocator_the_same_rec_is_double_counted(self):
        # This documents the bug: calling calculate_activity independently
        # per activity (no covered_kwh) lets both claim the full 3 MWh.
        calcs_a, _, _ = calculate_activity(self.activities[0], self.idx, region="ERCT", instruments=self.instruments)
        calcs_b, _, _ = calculate_activity(self.activities[1], self.idx, region="ERCT", instruments=self.instruments)
        mkt_a = next(c["co2e_kg"] for c in calcs_a if c["scope"] == "2_market")
        mkt_b = next(c["co2e_kg"] for c in calcs_b if c["scope"] == "dc_market")
        # Both got the full 3,000 kWh offset independently -- the bug.
        self.assertEqual(mkt_a, Decimal("45200") * Decimal("0.37368"))
        self.assertEqual(mkt_b, Decimal("4800") * Decimal("0.37368"))

    def test_allocator_splits_the_pool_so_it_is_only_spent_once(self):
        covered = allocate_rec_coverage(self.activities, self.instruments, self.region_by_site)
        # Deterministic id order: "act-cloud" < "act-elec-austin" alphabetically,
        # so the cloud facility (7,800 kWh) claims its 3,000 kWh first,
        # leaving nothing for the electricity bill.
        self.assertEqual(covered.get("act-cloud"), Decimal("3000"))
        self.assertNotIn("act-elec-austin", covered)

        calcs_cloud, _, _ = calculate_activity(
            self.activities[1], self.idx, region="ERCT",
            instruments=self.instruments, covered_kwh=covered.get("act-cloud", Decimal("0")),
        )
        calcs_elec, _, _ = calculate_activity(
            self.activities[0], self.idx, region="ERCT",
            instruments=self.instruments, covered_kwh=covered.get("act-elec-austin", Decimal("0")),
        )
        mkt_cloud = next(c["co2e_kg"] for c in calcs_cloud if c["scope"] == "dc_market")
        mkt_elec = next(c["co2e_kg"] for c in calcs_elec if c["scope"] == "2_market")
        # Cloud facility is 7,800 kWh; 3,000 kWh covered -> 4,800 kWh remainder.
        self.assertEqual(mkt_cloud, Decimal("4800") * Decimal("0.37368"))
        # Electricity bill gets none of the REC -> full 48,200 kWh at the residual-mix rate.
        self.assertEqual(mkt_elec, Decimal("48200") * Decimal("0.37368"))


class TestStaleFactorSetIsSeparate(unittest.TestCase):
    def test_stale_set_has_only_the_one_trap_row(self):
        idx = _index("v0-stale.csv")
        self.assertEqual(len(idx), 1)
        self.assertIn(("electricity", "ERCT", "2_location"), idx)


if __name__ == "__main__":
    unittest.main()
