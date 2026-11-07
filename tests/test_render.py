"""The report headline is fully derived from its Report, not hard-coded seed values."""

from decimal import Decimal

from carbon_room.models import Report
from carbon_room.report.render import pack


def test_report_headline_uses_supplied_numbers(factor_db, close_id):
    report = Report(
        close_id,
        1,
        Decimal("7.25"),
        Decimal("0.75"),
        Decimal("91"),
        "3/4",
        [],
        [],
        [],
        None,
        [],
        ["General information for a human reviewer, not legal advice."],
        None,
        None,
    )
    markdown, html = pack(report, factor_db)
    assert (
        "October total (verified only): 7.25 tCO2e. Unverified, excluded: 0.75 tCO2e. Gaps: 0. Coverage: 91% verified."
        in markdown
    )
    assert "7.25" in html and "91%" in html
    assert "no data, not zero" in markdown
