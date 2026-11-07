"""F6 source tags, deterministic rendering, trace and role-gated publishing."""

from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pdfplumber
import pytest

from carbon_room import collect
from carbon_room.actors import WATCHDOG
from carbon_room.calc import run as calc_run
from carbon_room.ledger import ledger
from carbon_room.models import Actor, Finding, NeedsRoomEvent, NotAllowed, Option
from carbon_room.report import pdf, publish, render, reporter, trace

LEAD = Actor("human", "lead", "Lead", "lead")
FINANCE = Actor("human", "finance", "Finance", "finance")


def test_draft_tags_only_verified_reportable_rows_and_traces_source(factor_db, close_id, add_claim):
    verified = add_claim(close_id, "dc-eu-west", "dc_it_kwh", "12000", pue="1.2", market_based_kgco2e="0")
    excluded = add_claim(close_id, "hq", "diesel_l", "100")
    calc_run.calculate(factor_db, close_id)
    ledger.set_status(factor_db, verified, "VERIFIED", WATCHDOG, "test")
    draft = reporter.draft(factor_db, close_id)
    assert draft.verified_total_tCO2e == Decimal("3.8983536")
    assert draft.unverified_excluded_tCO2e == Decimal("0.258354")
    assert len(draft.s_tags) == 2
    assert draft.s_tags[0].activity == "dc_it_kwh"
    assert draft.s_tags[0].tag == "S-001"
    assert draft.s_tags[1].tag == "S-002"
    assert "as reported by vendor" in draft.s_tags[1].recompute
    assert draft.s_tags[0].status == "VERIFIED"
    assert ledger.get_claim(factor_db, excluded).status == "UNVERIFIED"
    assert trace.lookup(factor_db, close_id, "S-001").sha256 == draft.s_tags[0].sha256
    markdown, html = render.pack(draft, factor_db)
    assert "verified only" in markdown
    assert "UNVERIFIED" in markdown
    assert "S-001" in markdown
    assert "no data, not zero" in markdown
    assert "1920" in html and "1080" in html


def test_publish_guards_and_open_gap_exclusion(factor_db, close_id, add_claim, tmp_path, monkeypatch):
    verified = add_claim(close_id, "hq", "electricity_kwh", "1000")
    unverified = add_claim(close_id, "hq", "diesel_l", "100")
    calc_run.calculate(factor_db, close_id)
    ledger.set_status(factor_db, verified, "VERIFIED", WATCHDOG, "test")
    finding = Finding(
        "F-open",
        "R5",
        "VARIANCE",
        [unverified],
        "hq",
        "2026-10",
        "lead",
        "Needs review",
        ["test"],
        [Option("approve", "approve", "Approve")],
        2,
        True,
    )
    ledger.upsert_gap(factor_db, close_id, finding)
    monkeypatch.setattr(publish, "OUTPUT_ROOT", tmp_path)
    with pytest.raises(NeedsRoomEvent):
        publish.publish(factor_db, close_id, LEAD, None)
    with pytest.raises(NotAllowed):
        publish.publish(factor_db, close_id, FINANCE, "msg-finance")
    result = publish.publish(factor_db, close_id, LEAD, "msg-publish")
    assert result.approver == "lead"
    assert len(result.gaps) == 1
    assert result.verified_total_tCO2e == Decimal("0.19503700802971")
    assert (tmp_path / "2026-10" / "v1" / "report.json").exists()
    assert (tmp_path / "2026-10" / "v1" / "report.md").exists()
    assert (tmp_path / "2026-10" / "v1" / "coverage.html").exists()
    pdf_path = tmp_path / "2026-10" / "v1" / "report.pdf"
    assert pdf_path.exists() and pdf_path.stat().st_size > 1000
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert pdf.render(result, factor_db) == pdf_path.read_bytes()
    with pdfplumber.open(BytesIO(pdf_path.read_bytes())) as rendered:
        pdf_text = "\n".join(page.extract_text() or "" for page in rendered.pages)
    assert all(item in pdf_text for item in ("UNVERIFIED", "G-1", "S-001", "no data, not zero"))
    with pytest.raises(ValueError, match="already published"):
        publish.publish(factor_db, close_id, LEAD, "msg-again")
    assert ledger.get_close(factor_db, close_id)["published_message_id"] == "msg-publish"
    assert any(
        item["subject_type"] == "publish" and item["decision"] == "approve"
        for item in ledger.get_approvals(factor_db, close_id)
    )
    with pytest.raises(ValueError, match="published close"):
        calc_run.calculate(factor_db, close_id)
    with pytest.raises(NotAllowed, match="published close"):
        collect.ingest(factor_db, close_id, WATCHDOG)
    with pytest.raises(NotAllowed, match="published close"):
        collect.ingest_file(factor_db, close_id, tmp_path / "missing.pdf", LEAD, chat_message_id="msg-upload")
    with pytest.raises(NotAllowed, match="published close"):
        ledger.set_status(factor_db, verified, "UNVERIFIED", WATCHDOG, "late change")
    with pytest.raises(NotAllowed, match="published close"):
        ledger.add_source(factor_db, ledger.get_sources(factor_db, close_id)[0], WATCHDOG)
    with pytest.raises(NotAllowed, match="published close"):
        ledger.add_claim(factor_db, ledger.get_claim(factor_db, verified), WATCHDOG)
    with pytest.raises(NotAllowed, match="published close"):
        ledger.set_factor(
            factor_db,
            verified,
            ledger.get_claim(factor_db, verified).factor_id,
            ledger.get_claim(factor_db, verified).factor_version,
            WATCHDOG,
            "late change",
        )
    with pytest.raises(NotAllowed, match="published close"):
        ledger.add_calculation(factor_db, ledger.latest_calculation(factor_db, verified))
    with pytest.raises(NotAllowed, match="published close"):
        ledger.upsert_gap(factor_db, close_id, finding)
    with pytest.raises(NotAllowed, match="published close"):
        ledger.set_gap_thread(factor_db, close_id, "G-1", "msg-late-thread")
    with pytest.raises(NotAllowed, match="published close"):
        ledger.resolve_gap(factor_db, close_id, "G-1", LEAD, "msg-late-resolve", {"action": "reject"})
    with pytest.raises(NotAllowed, match="published close"):
        ledger.add_approval(factor_db, close_id, "claim", verified, 2, LEAD, "approve", "late", "msg-late")
    with pytest.raises(NotAllowed, match="published close"):
        ledger.assign_s_tags(factor_db, close_id, 1, [ledger.latest_calculation(factor_db, verified).calc_id])
    with pytest.raises(NotAllowed, match="published close"):
        ledger.set_phase(factor_db, close_id, "OPEN", WATCHDOG)


def test_publish_output_write_failure_leaves_no_partial_version(factor_db, close_id, add_claim, tmp_path, monkeypatch):
    claim_id = add_claim(close_id, "hq", "electricity_kwh", "1000")
    calc_run.calculate(factor_db, close_id)
    ledger.set_status(factor_db, claim_id, "VERIFIED", WATCHDOG, "test")
    monkeypatch.setattr(publish, "OUTPUT_ROOT", tmp_path)
    original = Path.write_text

    def fail_markdown(path, content, *args, **kwargs):
        if path.name == "report.md":
            raise OSError("simulated disk write failure")
        return original(path, content, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_markdown)
    with pytest.raises(OSError, match="simulated disk write failure"):
        publish.publish(factor_db, close_id, LEAD, "msg-publish")
    assert not (tmp_path / "2026-10" / "v1").exists()
    assert ledger.get_close(factor_db, close_id)["phase"] != "PUBLISHED"
