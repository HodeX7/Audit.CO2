"""The report presents explicit cautions, not a legal conclusion."""

from decimal import Decimal

from carbon_room.models import CloseSummary, DcLine
from carbon_room.report.compliance import flags


def test_incomplete_zero_market_and_ai_line_get_all_four_cautions():
    line = DcLine(Decimal("10"), Decimal("0"), Decimal("1.2"), "certificate note", "UNVERIFIED", "vendor missing")
    summary = CloseSummary("2026-10-v1", "CHECKING", Decimal("10"), Decimal("5"), Decimal("67"), 4, 3, [], line)
    result = flags(summary)
    assert result[0] == "General information for a human reviewer, not legal advice."
    assert len(result) == 5
    assert any("Do not describe this total as complete." in item for item in result)
    assert any("Label the market-based figure as certificate-based." in item for item in result)
    assert any("State that the AI line is unverified." in item for item in result)
    assert any("Do not imply that unlisted Scope 3 categories are zero." in item for item in result)


def test_complete_report_without_dc_has_fewer_cautions():
    summary = CloseSummary("2026-10-v1", "CHECKING", Decimal("10"), Decimal("0"), Decimal("100"), 1, 1, [], None)
    result = flags(summary)
    assert len(result) == 2  # Disclaimer and configured Scope 3 disclosure only.
