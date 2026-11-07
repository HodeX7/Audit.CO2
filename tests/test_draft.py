"""Drafting is stable and source tags never attach to unverified rows."""

from carbon_room.actors import WATCHDOG
from carbon_room.calc import run as calc_run
from carbon_room.ledger import ledger
from carbon_room.report import reporter


def test_repeated_draft_keeps_tags_and_does_not_rewrite_audit(factor_db, close_id):
    from decimal import Decimal

    from carbon_room.actors import CALCULATOR
    from carbon_room.models import Claim, Source

    source = Source(
        "SRC-draft",
        close_id,
        "hq",
        "utility_pdf",
        "hq_2026-10.pdf",
        "stored",
        "sha-draft",
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
    first = reporter.draft(factor_db, close_id)
    events = factor_db.execute("SELECT COUNT(*) FROM events WHERE close_id=?", (close_id,)).fetchone()[0]
    second = reporter.draft(factor_db, close_id)
    assert first == second
    assert [tag.tag for tag in second.s_tags] == ["S-001"]
    assert ledger.get_close(factor_db, close_id)["phase"] == "DRAFTED"
    assert factor_db.execute("SELECT COUNT(*) FROM events WHERE close_id=?", (close_id,)).fetchone()[0] == events
