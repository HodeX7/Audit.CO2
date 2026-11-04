"""Tests for carbonroom/report. The approval-gate tests are the most
important ones here — they prove Honesty Rule 1 ("no one writes directly
to the published total") actually holds in code, not just in the docs.

Run with: python3 -m unittest tests.test_report -v
"""

import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from carbonroom.calc import load_factor_set
from carbonroom.report import ApprovalRecord, PublishRefusedError, build_report, publish_report, render_markdown

FACTORS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "factors"


def _build_fixture():
    sites = [
        {"id": "austin", "name": "Austin Plant", "grid_subregion": "ERCT"},
        {"id": "reno", "name": "Reno Office", "grid_subregion": "NWPP"},
    ]
    factors = load_factor_set(FACTORS_DIR / "v1-2026-10.csv")

    activities = [
        {"id": "act-ng", "site_id": "austin", "period_id": "2026-10", "category": "natural_gas",
         "quantity": "120", "unit": "mmbtu", "status": "VERIFIED",
         "source_doc_id": "doc-ng", "excerpt": "120 mmBtu billed", "excerpt_locator": "p1",
         "excerpt_sha256": "sha-ng"},
        {"id": "act-elec-austin", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "48200", "unit": "kwh", "status": "VERIFIED",
         "source_doc_id": "doc-elec-austin", "excerpt": "48,200 kWh", "excerpt_locator": "p1",
         "excerpt_sha256": "sha-elec-austin"},
        {"id": "act-elec-reno", "site_id": "reno", "period_id": "2026-10", "category": "electricity",
         "quantity": "10000", "unit": "kwh", "status": "VERIFIED",
         "source_doc_id": "doc-elec-reno", "excerpt": "10,000 kWh", "excerpt_locator": "p1",
         "excerpt_sha256": "sha-elec-reno"},
        {"id": "act-cloud", "site_id": "austin", "period_id": "2026-10", "category": "cloud_compute",
         "quantity": "5000", "unit": "kwh", "status": "VERIFIED",
         "source_doc_id": "doc-cloud", "excerpt": "5,000 kWh IT load", "excerpt_locator": "p2",
         "excerpt_sha256": "sha-cloud", "extra_json": {"pue": "1.2", "wue": "0.6"}},
        # Still unverified -> must be excluded from the headline total.
        {"id": "act-elec-unverified", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "1000", "unit": "kwh", "status": "UNVERIFIED", "source_doc_id": "doc-elec-extra"},
    ]

    def calc(activity_id, factor_id, scope, co2e_kg):
        return {"id": f"calc-{activity_id}-{scope}", "activity_id": activity_id, "factor_id": factor_id,
                "scope": scope, "co2e_kg": co2e_kg, "code_version": "calc-0.1.0"}

    calculations = [
        calc("act-ng", "ef-natgas-us-1-v1", "1", Decimal("120") * Decimal("53.117")),
        calc("act-elec-austin", "ef-elec-erct-loc-v1", "2_location", Decimal("48200") * Decimal("0.33413")),
        calc("act-elec-austin", "ef-elec-erct-mkt-v1", "2_market", Decimal("48200") * Decimal("0.37368")),
        calc("act-elec-reno", "ef-elec-nwpp-loc-v1", "2_location", Decimal("10000") * Decimal("0.28815")),
        calc("act-elec-reno", "ef-elec-nwpp-mkt-v1", "2_market", Decimal("10000") * Decimal("0.29780")),
        calc("act-cloud", "ef-elec-erct-loc-v1", "dc_location", Decimal("5000") * Decimal("1.2") * Decimal("0.33413")),
        calc("act-cloud", "ef-elec-erct-mkt-v1", "dc_market", Decimal("5000") * Decimal("1.2") * Decimal("0.37368")),
        calc("act-elec-unverified", "ef-elec-erct-loc-v1", "2_location", Decimal("1000") * Decimal("0.33413")),
    ]

    gaps = [
        {"id": "gap-1", "period_id": "2026-10", "kind": "missing_doc", "status": "OPEN",
         "owner_handle": "lena", "resolution": None},
    ]
    return dict(
        company="Brightwell Manufacturing", period_id="2026-10", sites=sites,
        activities=activities, calculations=calculations, factors=factors, gaps=gaps,
    )


class TestBuildReport(unittest.TestCase):
    def setUp(self):
        self.report = build_report(**_build_fixture())

    def test_status_starts_as_draft(self):
        self.assertEqual(self.report["status"], "DRAFT")
        self.assertIsNone(self.report["approver"])

    def test_scope_totals_use_only_verified_rows(self):
        t = self.report["totals_t_co2e"]
        expected_scope1 = Decimal("120") * Decimal("53.117") / 1000
        expected_loc = (Decimal("48200") * Decimal("0.33413") + Decimal("10000") * Decimal("0.28815")) / 1000
        expected_mkt = (Decimal("48200") * Decimal("0.37368") + Decimal("10000") * Decimal("0.29780")) / 1000
        self.assertAlmostEqual(float(t["scope1"]), float(expected_scope1), places=2)
        self.assertAlmostEqual(float(t["scope2_location"]), float(expected_loc), places=2)
        self.assertAlmostEqual(float(t["scope2_market"]), float(expected_mkt), places=2)

    def test_data_centre_line_is_separate_from_scope1_2(self):
        dc = self.report["data_centre"]
        self.assertEqual(dc["scope"], "3 (Cat 1, purchased cloud services)")
        self.assertAlmostEqual(float(dc["facility_kwh"]), 6000.0, places=2)   # 5000 x 1.2
        self.assertAlmostEqual(float(dc["water_l"]), 3000.0, places=2)       # 5000 x 0.6
        expected_dc_loc = Decimal("5000") * Decimal("1.2") * Decimal("0.33413") / 1000
        self.assertAlmostEqual(float(dc["co2e_location_t"]), float(expected_dc_loc), places=2)

    def test_unverified_activity_excluded_from_headline_but_counted_separately(self):
        expected_excluded = Decimal("1000") * Decimal("0.33413") / 1000
        self.assertAlmostEqual(float(self.report["unverified_excluded_t_co2e"]), float(expected_excluded), places=2)
        reasons = {i["activity_id"]: i["reason"] for i in self.report["unverified_items"]}
        self.assertEqual(reasons["act-elec-unverified"], "UNVERIFIED")
        self.assertNotIn("act-elec-unverified", [v["activity_id"] for v in self.report["verified_items"]])

    def test_coverage_pct_is_verified_over_verified_plus_unverified(self):
        verified_total = (self.report["totals_t_co2e"]["scope1"] + self.report["totals_t_co2e"]["scope2_location"]
                           + self.report["data_centre"]["co2e_location_t"])
        excluded = self.report["unverified_excluded_t_co2e"]
        expected = float(verified_total / (verified_total + excluded) * 100)
        self.assertAlmostEqual(self.report["coverage_pct"], round(expected, 1), places=1)

    def test_evidence_index_has_source_for_every_verified_item(self):
        verified_ids = {v["activity_id"] for v in self.report["verified_items"]}
        evidence_ids = {e["activity_id"] for e in self.report["evidence_index"]}
        self.assertTrue(verified_ids.issubset(evidence_ids))
        for e in self.report["evidence_index"]:
            self.assertIsNotNone(e["source_doc"])
            self.assertIsNotNone(e["sha256"])

    def test_open_gap_is_listed(self):
        self.assertEqual(len(self.report["gaps"]), 1)
        self.assertEqual(self.report["gaps"][0]["gap_id"], "gap-1")

    def test_report_hash_changes_if_numbers_change(self):
        fixture2 = _build_fixture()
        fixture2["activities"][0]["quantity"] = "121"  # tiny change
        report2 = build_report(**fixture2)
        self.assertNotEqual(self.report["report_sha256"], report2["report_sha256"])

    def test_markdown_renders_without_error_and_contains_key_numbers(self):
        md = render_markdown(self.report)
        self.assertIn("Brightwell Manufacturing", md)
        self.assertIn("Coverage", md)
        self.assertIn("gap-1", md)


class TestPublishGate(unittest.TestCase):
    """Honesty Rule 1, enforced: no publish without a real, matching
    human approval. This is the most important test in the whole repo."""

    def setUp(self):
        self.report = build_report(**_build_fixture())

    def test_publish_refused_with_no_approvals_at_all(self):
        with self.assertRaises(PublishRefusedError):
            publish_report(self.report, approvals=[])

    def test_publish_refused_with_a_rejection(self):
        approvals = [ApprovalRecord("2026-10", "grace", "REJECT", self.report["report_sha256"]).to_row("appr-1")]
        with self.assertRaises(PublishRefusedError):
            publish_report(self.report, approvals)

    def test_publish_refused_if_approval_hash_does_not_match(self):
        # Approval was for a different (e.g. earlier/stale) version of the numbers.
        approvals = [ApprovalRecord("2026-10", "grace", "APPROVE", "deadbeef" * 8).to_row("appr-2")]
        with self.assertRaises(PublishRefusedError):
            publish_report(self.report, approvals)

    def test_publish_refused_for_wrong_period(self):
        approvals = [ApprovalRecord("2026-09", "grace", "APPROVE", self.report["report_sha256"]).to_row("appr-3")]
        with self.assertRaises(PublishRefusedError):
            publish_report(self.report, approvals)

    def test_publish_succeeds_with_a_real_matching_approval(self):
        approvals = [ApprovalRecord("2026-10", "grace", "APPROVE", self.report["report_sha256"]).to_row("appr-4")]
        published = publish_report(self.report, approvals)
        self.assertEqual(published["status"], "PUBLISHED")
        self.assertEqual(published["approver"], "grace")

    def test_cannot_republish_an_already_published_report(self):
        approvals = [ApprovalRecord("2026-10", "grace", "APPROVE", self.report["report_sha256"]).to_row("appr-5")]
        published = publish_report(self.report, approvals)
        with self.assertRaises(PublishRefusedError):
            publish_report(published, approvals)

    def test_approval_does_not_carry_over_if_numbers_change_after_approval(self):
        approvals = [ApprovalRecord("2026-10", "grace", "APPROVE", self.report["report_sha256"]).to_row("appr-6")]
        fixture2 = _build_fixture()
        fixture2["activities"][0]["quantity"] = "999"  # numbers changed after Grace approved
        new_report = build_report(**fixture2)
        with self.assertRaises(PublishRefusedError):
            publish_report(new_report, approvals)


if __name__ == "__main__":
    unittest.main()
