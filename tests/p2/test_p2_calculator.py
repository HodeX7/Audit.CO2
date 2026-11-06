"""Checklist stories 2.2, 2.3 and 2.5. Expected values are multiplied out by hand, not taken from the code."""

from decimal import Decimal

import pytest

from carbon_room import core
from carbon_room.calc import calculator, run
from carbon_room.ledger import ledger
from carbon_room.models import Claim

D = Decimal
EGRID = ("EGRID-2023-CAMX-electricity_kwh", "2023", "0.19503700802971", "kgCO2e/kWh")
DEFRA_ELEC = ("DEFRA-2026-UK-electricity_kwh", "2026", "0.13096", "kgCO2e/kWh")
DEFRA_DIESEL = ("DEFRA-2026-UK-diesel_l", "2026", "2.58354", "kgCO2e/L")


def factor(spec):
    factor_id, version, value, unit = spec
    return {"factor_id": factor_id, "version": version, "value": value, "unit": unit}


def claim(activity="electricity_kwh", value="48300", unit="kWh", site="hq"):
    return Claim("CL-X", "2026-10-v1", site, "2026-10", activity, D(value), unit, "2", "SRC-1", "x", "sha", 0,
                 None, None, "UNVERIFIED", "collector", None, None, {})


# 2.2 compute ---------------------------------------------------------------------------------------------------------

def test_the_checklist_example_formula_is_reproduced_exactly():
    calc = calculator.compute(claim(value="48200"), factor(("X", "1", "0.20705", "kgCO2e/kWh")))
    assert calc.formula == "48200 kWh × 0.20705 kgCO2e/kWh = 9979.81 kgCO2e"
    assert calc.kgco2e == D("9979.81")


def test_electricity_matches_a_hand_calculation_and_is_location_based():
    calc = calculator.compute(claim(), factor(EGRID))
    assert calc.kgco2e == D("9420.287487834993")  # 48300 x 0.19503700802971
    assert calc.basis == "location"
    assert (calc.calc_id, calc.claim_id, calc.factor_id) == ("", "CL-X", "EGRID-2023-CAMX-electricity_kwh")
    assert isinstance(calc.kgco2e, Decimal)


def test_diesel_matches_a_hand_calculation_and_has_no_basis():
    calc = calculator.compute(claim("diesel_l", "2000", "L"), factor(DEFRA_DIESEL))
    assert calc.kgco2e == D("5167.08")  # 2000 x 2.58354
    assert calc.basis is None


def test_activity_is_converted_to_the_factor_unit_first():
    calc = calculator.compute(claim(value="48.3", unit="MWh"), factor(DEFRA_ELEC))
    assert calc.kgco2e == D("6325.368")  # 48.3 MWh = 48,300 kWh x 0.13096
    assert calc.formula.startswith("48300 kWh ×")


def test_compute_is_pure_and_repeatable():
    first = calculator.compute(claim(), factor(EGRID))
    assert first == calculator.compute(claim(), factor(EGRID))


def test_data_centre_claims_are_not_priced_here():
    with pytest.raises(ValueError, match="data-centre"):
        calculator.compute(claim("dc_it_kwh", "12000"), factor(("X", "1", "0.27", "kgCO2e/kWh")))


# 2.5 recompute -------------------------------------------------------------------------------------------------------

def test_recompute_matches_what_was_stored():
    stored = calculator.compute(claim(), factor(EGRID))
    formula, kg, matches = calculator.recompute(stored, claim(), factor(EGRID))
    assert matches and kg == stored.kgco2e and formula == stored.formula


def test_recompute_detects_a_changed_result_input_or_factor():
    stored = calculator.compute(claim(), factor(EGRID))
    stored.kgco2e += D("0.001")
    assert calculator.recompute(stored, claim(), factor(EGRID))[2] is False
    stored = calculator.compute(claim(), factor(EGRID))
    assert calculator.recompute(stored, claim(value="48301"), factor(EGRID))[2] is False
    assert calculator.recompute(stored, claim(), factor(DEFRA_ELEC))[2] is False


# 2.3 calculate -------------------------------------------------------------------------------------------------------

@pytest.fixture
def october(factor_db, close_id, add_claim):
    ids = {
        "hq_elec": add_claim(close_id, "hq", "electricity_kwh", 48300),
        "hq_elec_sep": add_claim(close_id, "hq", "electricity_kwh", 35000, month="2026-09"),
        "diesel": add_claim(close_id, "hq", "diesel_l", 2000),
        "w2": add_claim(close_id, "warehouse-2", "electricity_kwh", 18000),
        "dc": add_claim(close_id, "dc-eu-west", "dc_it_kwh", 12000, pue="1.2"),
    }
    return ids


def test_each_claim_is_priced_with_the_factor_its_site_and_activity_call_for(factor_db, close_id, october):
    run.calculate(factor_db, close_id)
    used = {name: ledger.get_claim(factor_db, cid).factor_id for name, cid in october.items()}
    assert used["hq_elec"] == "EGRID-2023-CAMX-electricity_kwh"
    assert used["hq_elec_sep"] == "EGRID-2023-CAMX-electricity_kwh"  # the prior month is priced too, as a baseline
    assert used["diesel"] == "DEFRA-2026-UK-diesel_l"
    assert used["w2"] == "DEFRA-2026-UK-electricity_kwh"


def test_the_october_hq_electricity_claim_gets_the_expected_calculation(factor_db, close_id, october):
    run.calculate(factor_db, close_id)
    calc = ledger.latest_calculation(factor_db, october["hq_elec"])
    assert calc.kgco2e == D("9420.287487834993")
    assert (calc.factor_id, calc.factor_version, calc.basis) == ("EGRID-2023-CAMX-electricity_kwh", "2023", "location")


def test_the_factor_choice_is_recorded_on_the_claim_and_in_the_audit_log(factor_db, close_id, october):
    run.calculate(factor_db, close_id)
    events = factor_db.execute("SELECT actor, reason FROM events WHERE kind='factor_set' AND claim_id=?",
                               (october["w2"],)).fetchall()
    assert [(e["actor"], e["reason"]) for e in events] == [("calculator", "factor chosen at calculation")]
    assert ledger.get_claim(factor_db, october["w2"]).factor_version == "2026"


def test_data_centre_claims_are_left_alone(factor_db, close_id, october):
    results = run.calculate(factor_db, close_id)
    assert ledger.latest_calculation(factor_db, october["dc"]) is None
    assert len(results) == 4


def test_running_twice_adds_no_calculations_and_no_events(factor_db, close_id, october):
    run.calculate(factor_db, close_id)
    calcs = factor_db.execute("SELECT COUNT(*) FROM calculations").fetchone()[0]
    events = factor_db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    run.calculate(factor_db, close_id)
    assert factor_db.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == calcs == 4
    assert factor_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == events


def test_a_factor_a_human_chose_is_respected_and_the_old_calculation_is_superseded(factor_db, close_id, october):
    run.calculate(factor_db, close_id)
    ledger.set_factor(factor_db, october["w2"], "DEFRA-2026-UK-diesel_l", "2026", core_actor(), "test")
    run.calculate(factor_db, close_id)
    assert ledger.get_claim(factor_db, october["w2"]).factor_id == "DEFRA-2026-UK-diesel_l"
    assert factor_db.execute("SELECT COUNT(*) FROM calculations WHERE claim_id=?", (october["w2"],)).fetchone()[0] == 2
    assert ledger.latest_calculation(factor_db, october["w2"]).factor_id == "DEFRA-2026-UK-diesel_l"


def core_actor():
    from carbon_room.actors import WATCHDOG

    return WATCHDOG


def test_the_phase_moves_to_calculating_only_from_the_early_phases(factor_db, close_id, october):
    run.calculate(factor_db, close_id)
    assert ledger.get_close(factor_db, close_id)["phase"] == "CALCULATING"
    ledger.set_phase(factor_db, close_id, "AWAITING_HUMANS", core_actor())
    run.calculate(factor_db, close_id)
    assert ledger.get_close(factor_db, close_id)["phase"] == "AWAITING_HUMANS"


def test_a_missing_catalogue_row_names_the_site_and_activity(db):
    from carbon_room import actors, config
    from carbon_room.calc import factors

    close = ledger.create_close(db, "2026-10", ["hq"], config.load_config()["default_factor_set"], actors.CALCULATOR, "m")
    db.commit()
    with pytest.raises(factors.FactorNotFound, match="hq"):
        run.choose_factor(db, ledger.get_close(db, close), claim())


def test_core_calculate_is_wired_to_the_calculator(factor_db, close_id, october, monkeypatch):
    monkeypatch.setattr(core, "connect", lambda: factor_db)
    assert len(core.calculate(close_id)) == 4
