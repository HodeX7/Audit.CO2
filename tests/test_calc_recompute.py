"""F7: every published tagged value recomputes and retains its source excerpt."""

from decimal import Decimal
from pathlib import Path

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.calc.calculator import recompute
from carbon_room.checks import resolve
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger
from carbon_room.ledger.audit import verify_audit
from carbon_room.models import Actor
from carbon_room.report import publish, trace


def test_every_seed_calculation_recomputes_before_resolutions(factor_db, close_id):
    collect.ingest(factor_db, close_id, CALCULATOR)
    calculations = calc_run.calculate(factor_db, close_id)
    assert len(calculations) == 11
    for calculation in calculations:
        claim = ledger.get_claim(factor_db, calculation.claim_id)
        factor = ledger.get_factor(factor_db, calculation.factor_id)
        assert recompute(calculation, claim, factor)[2]


def test_every_published_tag_recomputes_from_verbatim_evidence(factor_db, close_id, monkeypatch, tmp_path):
    collect.ingest(factor_db, close_id, CALCULATOR)
    calc_run.calculate(factor_db, close_id)
    check_run.check(factor_db, close_id)
    lead = Actor("human", "lead", "Lead", "lead")

    def gap(rule):
        return next(item for item in ledger.get_gaps(factor_db, close_id, status="OPEN") if item.rule == rule)

    pick = gap("R2").options[0]
    resolve.apply(factor_db, gap("R2").gap_id, "pick", lead, "msg-pick", pick.params)
    stale = gap("R3")
    option = next(item for item in stale.options if item.action == "approve")
    resolve.apply(factor_db, stale.gap_id, "approve", lead, "msg-stale", option.params)
    resolve.apply(factor_db, gap("R5").gap_id, "approve", lead, "msg-variance", {})
    factor_db.commit()
    upload = Path(__file__).resolve().parents[1] / "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf"
    resolve.apply(
        factor_db,
        gap("R4").gap_id,
        "upload",
        Actor("human", "priya", "Priya", "site_manager"),
        "msg-upload",
        {"path": str(upload)},
    )
    monkeypatch.setattr(publish, "OUTPUT_ROOT", tmp_path)
    report = publish.publish(factor_db, close_id, lead, "msg-publish")
    assert report.s_tags
    assert report.gaps == []
    assert report.verified_total_tCO2e == Decimal("21.941897087834993")
    assert report.source_coverage == "4/4"
    assert report.coverage_pct == 100
    assert (
        sum(tag.kgco2e for tag in report.s_tags if "as reported by vendor" not in tag.recompute) / 1000
        == report.verified_total_tCO2e
    )
    sources = {source.sha256: source for source in ledger.get_sources(factor_db, close_id)}
    for tag in report.s_tags:
        traced = trace.lookup(factor_db, close_id, tag.tag)
        assert "matches=True" in traced.recompute
        assert traced.excerpt in sources[traced.sha256].raw_text
        assert traced.status == "VERIFIED"
    assert verify_audit(factor_db, close_id).ok
