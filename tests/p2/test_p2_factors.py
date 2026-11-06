from decimal import Decimal

import pytest

from carbon_room import config
from carbon_room.calc import factors
from carbon_room.ledger import ledger


def test_catalogue_loads_and_every_row_is_cited(db):
    rows = factors.read_csv()
    assert len(rows) == 5
    assert all(row["citation"] for row in rows)
    assert factors.load(db) == 5
    assert factors.load(db) == 5  # identical repeat load is safe


def test_default_factor_set_is_configured_and_pins_three_sources():
    name = config.load_config()["default_factor_set"]
    assert factors.factor_set(name) == {"DEFRA": "2026", "EGRID": "2023", "EMBER": "2025"}
    with pytest.raises(ValueError, match="unknown factor set"):
        factors.factor_set("nope")


def test_locked_factor_follows_site_grid_and_fuel_config(factor_db, close_id):
    close = ledger.get_close(factor_db, close_id)
    expected = {
        ("hq", "electricity_kwh"): "EGRID-2023-CAMX-electricity_kwh",
        ("warehouse-2", "electricity_kwh"): "DEFRA-2026-UK-electricity_kwh",
        ("hq", "diesel_l"): "DEFRA-2026-UK-diesel_l",
        ("dc-eu-west", "dc_it_kwh"): "EMBER-2025-IE-dc_it_kwh",
    }
    for (site, activity), factor_id in expected.items():
        assert factors.locked_factor(factor_db, close, site, activity)["factor_id"] == factor_id


def test_missing_catalogue_row_names_the_site_and_activity(db):
    ledger.load_factors(db, [])
    close_id = ledger.create_close(db, "2026-10", ["hq"], "FS-2026-10", factors_actor(), "m")
    with pytest.raises(factors.FactorNotFound, match="hq"):
        factors.locked_factor(db, ledger.get_close(db, close_id), "hq", "electricity_kwh")


def factors_actor():
    from carbon_room import actors

    return actors.CALCULATOR


def test_vendor_reference_resolves_to_the_catalogue_row(factor_db):
    stale = factors.factor_from_ref(factor_db, "Ember 2024 IE")
    assert stale["factor_id"] == "EMBER-2024-IE-dc_it_kwh"
    assert Decimal(stale["value"]) == Decimal("0.270767")
    assert factors.factor_from_ref(factor_db, "Ember 2019 IE") is None
    assert factors.factor_from_ref(factor_db, "nonsense") is None


def test_is_locked_distinguishes_the_stale_edition(factor_db, close_id):
    close = ledger.get_close(factor_db, close_id)
    assert factors.is_locked(close, ledger.get_factor(factor_db, "EMBER-2025-IE-dc_it_kwh"))
    assert not factors.is_locked(close, ledger.get_factor(factor_db, "EMBER-2024-IE-dc_it_kwh"))


def test_bad_rows_are_rejected(tmp_path):
    good = factors.default_csv().read_text(encoding="utf-8").splitlines()
    path = tmp_path / "factors.csv"
    path.write_text("\n".join([good[0], good[1].replace("0.13096", "abc")]), encoding="utf-8")
    with pytest.raises(ValueError, match="not a decimal"):
        factors.read_csv(path)
    path.write_text("\n".join([good[0], good[1].replace("kgCO2e/kWh", "kgCO2e/gallon")]), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown unit"):
        factors.read_csv(path)
