"""Tests for carbonroom/check — built around the exact six demo traps from
the brief's Section 5.6, so a passing test suite here is also a dry run of
the three-trap demo moment.

Run with: python3 -m unittest tests.test_check -v
"""

import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from carbonroom.calc import index_factors, load_factor_set
from carbonroom.check import (
    UnrecognizedResolutionError,
    promote_clean_activities,
    resolve_gap,
    run_checks,
)

FACTORS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "factors"


def _build_fixture():
    sites = [
        {"id": "austin", "name": "Austin Plant", "region": "US-TX", "grid_subregion": "ERCT",
         "owner_handle": "omar", "room": "cr-site-austin"},
        {"id": "reno", "name": "Reno Office", "region": "US-NV", "grid_subregion": "NWPP",
         "owner_handle": "lena", "room": "cr-site-reno"},
    ]
    periods = [
        {"id": "2026-09", "status": "CLOSED", "factor_set_version": "v1-2026-10"},
        {"id": "2026-10", "status": "OPEN", "factor_set_version": "v1-2026-10"},
    ]
    source_docs = [
        {"id": "doc-diesel-1", "kind": "fuel_invoice", "sha256": "a1", "superseded_by": None},
        {"id": "doc-diesel-2", "kind": "fuel_invoice", "sha256": "a2", "superseded_by": None},
        {"id": "doc-ng-oct", "kind": "utility_bill", "sha256": "b1", "superseded_by": None},
        {"id": "doc-elec-clean", "kind": "utility_bill", "sha256": "c1", "superseded_by": None},
        # The false-done trap: this was VERIFIED against doc-false-done,
        # but doc-false-done has since been corrected/replaced.
        {"id": "doc-false-done", "kind": "utility_bill", "sha256": "d1", "superseded_by": "doc-false-done-fixed"},
        {"id": "doc-false-done-fixed", "kind": "utility_bill", "sha256": "d2", "superseded_by": None},
    ]
    activities = [
        # Conflict trap: two diesel invoices, same delivery, different quantities.
        {"id": "act-diesel-1", "site_id": "austin", "period_id": "2026-10", "category": "diesel",
         "quantity": "500", "unit": "gallon", "source_doc_id": "doc-diesel-1",
         "status": "UNVERIFIED", "extra_json": {"delivery_id": "DEL-204"}},
        {"id": "act-diesel-2", "site_id": "austin", "period_id": "2026-10", "category": "diesel",
         "quantity": "550", "unit": "gallon", "source_doc_id": "doc-diesel-2",
         "status": "UNVERIFIED", "extra_json": {"delivery_id": "DEL-204"}},

        # Outlier trap: October natural gas is +60% vs September.
        {"id": "act-ng-oct", "site_id": "austin", "period_id": "2026-10", "category": "natural_gas",
         "quantity": "240", "unit": "mmbtu", "source_doc_id": "doc-ng-oct", "status": "UNVERIFIED"},

        # Stale-factor trap: VERIFIED using the old eGRID2022 factor set.
        {"id": "act-elec-stale", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "48200", "unit": "kwh", "source_doc_id": "doc-elec-clean", "status": "VERIFIED"},

        # False-done trap: VERIFIED, but its source doc was later superseded.
        {"id": "act-false-done", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "1000", "unit": "kwh", "source_doc_id": "doc-false-done", "status": "VERIFIED"},

        # A clean activity with nothing wrong -> should promote to VERIFIED.
        # Deliberately a different site+category than every trap above, so
        # it isn't swept into another activity's conflict/outlier group.
        {"id": "act-clean", "site_id": "reno", "period_id": "2026-10", "category": "natural_gas",
         "quantity": "5", "unit": "mmbtu", "source_doc_id": "doc-elec-clean", "status": "UNVERIFIED"},

        # Reno has NO October electricity activity at all -> missing_doc trap.
    ]
    prior_period_activities = [
        {"id": "act-ng-sep", "site_id": "austin", "period_id": "2026-09", "category": "natural_gas",
         "quantity": "150", "unit": "mmbtu", "source_doc_id": "doc-ng-sep", "status": "VERIFIED"},
    ]
    factor_index = index_factors(load_factor_set(FACTORS_DIR / "v1-2026-10.csv"))
    stale_index = index_factors(load_factor_set(FACTORS_DIR / "v0-stale.csv"))
    factors_by_id = {**factor_index, **stale_index}
    # index_factors keys by (category,region,scope); re-key by id for the checker.
    all_factor_rows = load_factor_set(FACTORS_DIR / "v1-2026-10.csv") + load_factor_set(FACTORS_DIR / "v0-stale.csv")
    factors_by_id = {row["id"]: row for row in all_factor_rows}

    calculations = [
        {"id": "calc-elec-stale", "activity_id": "act-elec-stale", "factor_id": "ef-elec-erct-loc-v0",
         "scope": "2_location", "co2e_kg": Decimal("16936.884"), "code_version": "calc-0.1.0"},
    ]
    instruments = [
        # REC quality trap: right region, wrong vintage for this period.
        {"id": "rec-wrong-vintage", "period_id": "2026-10", "kind": "REC", "mwh": "10",
         "region": "NWPP", "vintage": "2019"},
    ]
    expected_documents = [
        ("austin", "2026-10", "diesel"),
        ("austin", "2026-10", "natural_gas"),
        ("austin", "2026-10", "electricity"),
        ("reno", "2026-10", "electricity"),
    ]
    return dict(
        period_id="2026-10", sites=sites, periods=periods, activities=activities,
        prior_period_activities=prior_period_activities, source_docs=source_docs,
        calculations=calculations, factors=list(factors_by_id.values()), instruments=instruments,
        existing_gaps=[], expected_documents=expected_documents,
    )


class TestSixTraps(unittest.TestCase):
    def setUp(self):
        self.fixture = _build_fixture()
        self.result = run_checks(**self.fixture)

    def test_missing_doc_trap(self):
        kinds_sites = {(g["kind"], g["site_id"]) for g in self.result.new_gaps}
        self.assertIn(("missing_doc", "reno"), kinds_sites)

    def test_conflict_trap(self):
        conflict_gaps = [g for g in self.result.new_gaps if g["kind"] == "conflict"]
        self.assertEqual(len(conflict_gaps), 1)
        self.assertEqual(self.result.status_updates["act-diesel-1"], "CONFLICTING")
        self.assertEqual(self.result.status_updates["act-diesel-2"], "CONFLICTING")

    def test_outlier_trap(self):
        outlier_gaps = [g for g in self.result.new_gaps if g["kind"] == "outlier"]
        self.assertEqual(len(outlier_gaps), 1)
        self.assertEqual(self.result.status_updates["act-ng-oct"], "FLAGGED")

    def test_stale_factor_trap(self):
        stale_gaps = [g for g in self.result.new_gaps if g["kind"] == "stale_factor"]
        self.assertEqual(len(stale_gaps), 1)
        self.assertEqual(self.result.status_updates["act-elec-stale"], "FLAGGED")

    def test_false_done_trap_reopens_verified_row(self):
        fd_gaps = [g for g in self.result.new_gaps if g["kind"] == "excerpt_mismatch"]
        self.assertEqual(len(fd_gaps), 1)
        self.assertEqual(self.result.status_updates["act-false-done"], "FLAGGED")

    def test_rec_quality_trap(self):
        rec_gaps = [g for g in self.result.new_gaps if g["kind"] == "rec_quality"]
        self.assertEqual(len(rec_gaps), 1)
        self.assertEqual(self.result.instrument_updates["rec-wrong-vintage"], "flagged")

    def test_clean_activity_is_untouched_by_checks_and_can_be_promoted(self):
        self.assertNotIn("act-clean", self.result.status_updates)
        activities = self.fixture["activities"]
        promotions = promote_clean_activities(activities, set(self.result.status_updates.keys()))
        self.assertEqual(promotions.get("act-clean"), "VERIFIED")

    def test_idempotent_second_run_creates_no_duplicate_gaps(self):
        fixture2 = dict(self.fixture)
        fixture2["existing_gaps"] = self.result.new_gaps  # simulate gaps now persisted
        result2 = run_checks(**fixture2)
        self.assertEqual(result2.new_gaps, [])

    def test_gap_ids_and_dedupe_keys_are_stable_across_runs(self):
        fixture2 = dict(self.fixture)
        result2 = run_checks(**fixture2)
        ids1 = sorted(g["id"] for g in self.result.new_gaps)
        ids2 = sorted(g["id"] for g in result2.new_gaps)
        self.assertEqual(ids1, ids2)


class TestResolveGap(unittest.TestCase):
    def test_use_picks_one_excludes_the_other(self):
        gap = {"id": "gap-1", "kind": "conflict"}
        res = resolve_gap(gap, "use act-diesel-2", "omar", candidate_activity_ids=("act-diesel-1", "act-diesel-2"))
        self.assertEqual(res.gap_status, "RESOLVED")
        self.assertEqual(res.activity_status_updates["act-diesel-2"], "UNVERIFIED")
        self.assertEqual(res.activity_status_updates["act-diesel-1"], "EXCLUDED")

    def test_numeric_choice(self):
        gap = {"id": "gap-1", "kind": "conflict"}
        res = resolve_gap(gap, "2", "omar", candidate_activity_ids=("act-diesel-1", "act-diesel-2"))
        self.assertEqual(res.activity_status_updates["act-diesel-2"], "UNVERIFIED")
        self.assertEqual(res.activity_status_updates["act-diesel-1"], "EXCLUDED")

    def test_exclude_with_single_candidate(self):
        gap = {"id": "gap-2", "kind": "excerpt_mismatch"}
        res = resolve_gap(gap, "exclude: bad meter reading", "lena", candidate_activity_ids=("act-x",))
        self.assertEqual(res.activity_status_updates, {"act-x": "EXCLUDED"})
        self.assertEqual(res.gap_status, "RESOLVED")

    def test_accept_outlier_risk_touches_no_activity(self):
        gap = {"id": "gap-3", "kind": "outlier"}
        res = resolve_gap(gap, "accept: known seasonal spike, confirmed with finance", "maya",
                           candidate_activity_ids=("act-ng-oct",))
        self.assertEqual(res.gap_status, "ACCEPTED_RISK")
        self.assertEqual(res.activity_status_updates, {})

    def test_approve_sends_back_for_reverification(self):
        gap = {"id": "gap-4", "kind": "stale_factor"}
        res = resolve_gap(gap, "approve", "grace", candidate_activity_ids=("act-elec-stale",))
        self.assertEqual(res.activity_status_updates, {"act-elec-stale": "UNVERIFIED"})

    def test_unrecognized_text_raises(self):
        gap = {"id": "gap-5", "kind": "conflict"}
        with self.assertRaises(UnrecognizedResolutionError):
            resolve_gap(gap, "whatever lol", "omar", candidate_activity_ids=("act-1", "act-2"))

    def test_exclude_requires_single_candidate(self):
        gap = {"id": "gap-6", "kind": "conflict"}
        with self.assertRaises(UnrecognizedResolutionError):
            resolve_gap(gap, "exclude: not sure which", "omar", candidate_activity_ids=("act-1", "act-2"))


if __name__ == "__main__":
    unittest.main()
