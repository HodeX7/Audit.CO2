"""The checked-in P2 baseline is regenerated from ledger behavior, not hand-edited totals."""

from scripts.generate_expected import EXPECTED, generate


def test_expected_seed_results_match_current_pipeline():
    assert generate() == EXPECTED.read_text(encoding="utf-8")
