"""Trace reads the ledger and visibly detects arithmetic tampering."""

from decimal import Decimal

import pytest

from carbon_room.actors import CALCULATOR, WATCHDOG
from carbon_room.calc import run as calc_run
from carbon_room.ledger import ledger
from carbon_room.models import Actor, Claim, Source
from carbon_room.report import publish, reporter, trace


def test_trace_exposes_mismatch_and_publish_refuses_it(factor_db, close_id, tmp_path, monkeypatch):
    source = Source(
        "SRC-trace",
        close_id,
        "hq",
        "utility_pdf",
        "hq_2026-10.pdf",
        "stored",
        "sha-trace",
        1,
        "Billing period: 2026-10-01 to 2026-10-31\nUsage: 1000 kWh",
        "2026-10-01",
        "2026-10-31",
        "OK",
        None,
    )
    ledger.add_source(factor_db, source, CALCULATOR)
    claim = Claim(
        "",
        close_id,
        "hq",
        "2026-10",
        "electricity_kwh",
        Decimal("1000"),
        "kWh",
        "2",
        source.source_doc_id,
        "1000 kWh",
        source.sha256,
        0,
        None,
        None,
        "UNVERIFIED",
        "collector",
        None,
        None,
        {},
    )
    claim_id = ledger.add_claim(factor_db, claim, CALCULATOR)
    calc_run.calculate(factor_db, close_id)
    ledger.set_status(factor_db, claim_id, "VERIFIED", WATCHDOG, "test")
    report = reporter.draft(factor_db, close_id)
    assert "matches=True" in trace.lookup(factor_db, close_id, report.s_tags[0].tag).recompute
    factor_db.execute(
        "UPDATE calculations SET kgco2e='999' WHERE calc_id=?",
        (ledger.latest_calculation(factor_db, claim_id).calc_id,),
    )
    assert "matches=False" in trace.lookup(factor_db, close_id, report.s_tags[0].tag).recompute
    monkeypatch.setattr(publish, "OUTPUT_ROOT", tmp_path)
    with pytest.raises(ValueError, match="recomputation mismatch"):
        publish.publish(factor_db, close_id, Actor("human", "lead", "Lead", "lead"), "msg-publish")
