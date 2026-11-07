"""F7: fresh month and fully renamed sites retain the four gap categories."""

from pathlib import Path
from shutil import copyfile

from carbon_room import collect, config
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger
from scripts.make_seed import cloud, email_invoice, pdf

ROOT = Path(__file__).resolve().parents[1]


def test_renamed_sites_and_months_find_same_four_gaps(factor_db, tmp_path, monkeypatch):
    custom = tmp_path / "config"
    custom.mkdir()
    for name in ("carbon_room.yaml", "factors.csv", "compliance_checks.yaml"):
        copyfile(ROOT / "config" / name, custom / name)
    copyfile(ROOT / "tests/fixtures/renamed_config/sites.yaml", custom / "sites.yaml")
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(custom))
    monkeypatch.chdir(tmp_path)
    config.clear_caches()
    try:
        old = Path("data/seed/2027-02")
        new = Path("data/seed/2027-03")
        pdf(old / "site-alpha_electricity_2027-02.pdf", "site-alpha", "1 Feb 2027 – 28 Feb 2027", "Usage: 35,000 kWh")
        email_invoice(old / "site-alpha_diesel_2027-02.eml", "site-alpha", "2027-02-01 to 2027-02-28", "2,200", "102")
        pdf(old / "site-beta_electricity_2027-02.pdf", "site-beta", "1 Feb 2027 – 28 Feb 2027", "Usage: 18,000 kWh")
        cloud(old / "site-gamma_cloud_2027-02.json", "2027-02-01", "2027-02-28", "Ember 2025 IE")
        pdf(new / "site-alpha_electricity_2027-03.pdf", "site-alpha", "1 Mar 2027 – 31 Mar 2027", "Usage: 48,300 kWh")
        email_invoice(new / "site-alpha_diesel_2027-03.eml", "site-alpha", "2027-03-01 to 2027-03-31", "2,000", "103")
        email_invoice(
            new / "site-alpha_diesel_2027-03-rev.eml", "site-alpha", "2027-03-01 to 2027-03-31", "2,400", "103R"
        )
        pdf(new / "site-beta_electricity_2027-03.pdf", "site-beta", "1 Feb 2027 – 28 Feb 2027", "Usage: 17,500 kWh")
        cloud(new / "site-gamma_cloud_2027-03.json", "2027-03-01", "2027-03-31", "Ember 2024 IE")
        close_id = ledger.create_close(
            factor_db, "2027-03", ["site-alpha", "site-beta", "site-gamma"], "FS-2026-10", CALCULATOR, "msg-start"
        )
        factor_db.commit()
        ingested = collect.ingest(factor_db, close_id, CALCULATOR)
        assert ingested.failed_sources == []
        assert ingested.statement == "All 5 2027-03 sources collected."
        calc_run.calculate(factor_db, close_id)
        check_run.check(factor_db, close_id)
        gaps = ledger.get_gaps(factor_db, close_id, status="OPEN")
        assert {gap.rule for gap in gaps} == {"R2", "R3", "R4", "R5"}
        assert "site-alpha" in next(gap.title for gap in gaps if gap.rule == "R2")
        assert "site-gamma" in next(gap.title for gap in gaps if gap.rule == "R3")
        assert "site-beta" in next(gap.title for gap in gaps if gap.rule == "R4")
        assert "site-alpha" in next(gap.title for gap in gaps if gap.rule == "R5")
        assert all("warehouse-2" not in gap.title and "2026-10" not in gap.title for gap in gaps)
    finally:
        config.clear_caches()
