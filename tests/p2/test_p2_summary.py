"""F5 summary is a pure view over live, current-month ledger state."""

from decimal import Decimal

from carbon_room.actors import WATCHDOG
from carbon_room.calc import run as calc_run
from carbon_room.ledger import ledger
from carbon_room.report import summary


def test_summary_excludes_baselines_and_market_figures_and_does_not_write(factor_db, close_id, add_claim):
    current = add_claim(close_id, "hq", "electricity_kwh", "1000")
    add_claim(close_id, "hq", "diesel_l", "100")
    dc = add_claim(close_id, "dc-eu-west", "dc_it_kwh", "12000", pue="1.2", market_based_kgco2e="0")
    add_claim(close_id, "hq", "electricity_kwh", "9000", month="2026-09")
    calc_run.calculate(factor_db, close_id)
    ledger.set_status(factor_db, current, "VERIFIED", WATCHDOG, "test")
    ledger.set_status(factor_db, dc, "VERIFIED", WATCHDOG, "test")
    events = factor_db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    phase = ledger.get_close(factor_db, close_id)["phase"]
    result = summary.build(factor_db, close_id)
    assert result.verified_kgco2e == Decimal("0.19503700802971") * 1000 + Decimal("0.270719") * 12000 * Decimal("1.2")
    assert result.excluded_kgco2e == Decimal("2.58354") * 100
    assert result.coverage_pct == Decimal("94")
    assert (result.sources_expected, result.sources_verified) == (4, 2)
    assert result.dc_line.location_kgco2e == Decimal("3898.3536")
    assert result.dc_line.market_kgco2e == Decimal(0)
    assert result.dc_line.rec_flag == "Market-based 0 relies on certificates; certificate quality not verified"
    assert result.dc_line.ai_line_status == "UNVERIFIED"
    assert result.dc_line.note
    assert result.open_gaps == []
    assert factor_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == events
    assert ledger.get_close(factor_db, close_id)["phase"] == phase
    ledger.set_status(factor_db, current, "UNVERIFIED", WATCHDOG, "test")
    changed = summary.build(factor_db, close_id)
    assert changed.verified_kgco2e < result.verified_kgco2e


def test_empty_close_has_zero_coverage_and_no_fabricated_data_centre_line(factor_db, close_id):
    result = summary.build(factor_db, close_id)
    assert result.coverage_pct == 0
    assert result.verified_kgco2e == result.excluded_kgco2e == 0
    assert result.dc_line is None
