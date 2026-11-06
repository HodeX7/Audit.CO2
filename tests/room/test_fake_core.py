"""FakeCore behaviour (SPEC-01 section 6)."""

from __future__ import annotations

import inspect
import time
from decimal import Decimal

import pytest
from fakes.fake_core import FakeCore

from carbon_room import core
from carbon_room.models import (
    Actor,
    AuditCheck,
    Finding,
    IngestReport,
    NeedsRoomEvent,
    NotAllowed,
    NotFound,
    Option,
    Report,
)
from carbon_room.room.async_core import CORE_FUNCTIONS

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
PRIYA = Actor("human", "priya", "Priya", "site_manager")
GUEST = Actor("human", "guest:x", "x", None)
COLLECTOR = Actor("agent", "collector", "Collector")
G1_PARAMS = {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}


def run_to_check(fc):
    cid = fc.start_close("2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "h-1")
    fc.ingest(cid, COLLECTOR)
    fc.calculate(cid)
    fc.check(cid)
    return cid


def resolve_all(fc):
    fc.resolve("G-1", "upload", PRIYA, "h-2", {"path": "data/inbox/x.pdf", **G1_PARAMS})
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    fc.resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})
    fc.resolve("G-4", "approve", LEAD, "h-5", {})


def figures(fc, cid):
    s = fc.summary(cid)
    return (s.verified_kgco2e, s.excluded_kgco2e, s.coverage_pct, s.sources_verified)


def test_fake_core_signatures_match_core():
    for name in CORE_FUNCTIONS:
        fake = list(inspect.signature(getattr(FakeCore, name)).parameters.values())[1:]
        real = list(inspect.signature(getattr(core, name)).parameters.values())
        assert [p.name for p in fake] == [p.name for p in real], name
        assert [p.default for p in fake] == [p.default for p in real], name


def test_fake_core_has_every_core_function():
    public = {
        n for n, f in vars(core).items()
        if inspect.isfunction(f) and f.__module__ == core.__name__ and not n.startswith("_")
    }
    assert set(CORE_FUNCTIONS) == public
    for name in CORE_FUNCTIONS:
        assert callable(getattr(FakeCore, name))


def test_start_close_ids_per_month():
    fc = FakeCore()
    assert fc.start_close("2026-10", [], "FS", LEAD, "h-1") == "2026-10-v1"
    assert fc.start_close("2026-10", [], "FS", LEAD, "h-1") == "2026-10-v2"
    assert fc.start_close("2026-09", [], "FS", LEAD, "h-1") == "2026-09-v1"
    assert fc.latest_close() == "2026-09-v1"


def test_ingest_report():
    fc = FakeCore()
    cid = fc.start_close("2026-10", [], "FS", LEAD, "h-1")
    report = fc.ingest(cid, COLLECTOR)
    ids = ["CL-0001", "CL-0002", "CL-0003", "CL-0004", "CL-0005", "CL-0006", "CL-0007", "CL-0008", "CL-0009"]
    assert report == IngestReport(cid, 9, ids, [], "All 5 October sources collected.")
    assert fc.resume_state(cid)[0] == "COLLECTING"


def test_fake_scenario_after_check():
    fc = FakeCore()
    cid = run_to_check(fc)
    phase, gaps = fc.resume_state(cid)
    assert phase == "AWAITING_HUMANS"
    assert [g.gap_id for g in gaps] == ["G-1", "G-2", "G-3", "G-4"]
    assert [g.owner for g in gaps] == ["priya", "lead", "lead", "lead"]
    assert [g.kind for g in gaps] == ["PERIOD", "CONFLICTING", "STALE", "VARIANCE"]
    assert [[o.key for o in g.options] for g in gaps] == [
        ["upload"], ["pick A", "pick B"], ["approve", "reject"], ["approve", "reject"],
    ]
    s = fc.summary(cid)
    assert s.verified_kgco2e == Decimal("0")
    assert s.excluded_kgco2e == Decimal("29184")
    assert s.coverage_pct == Decimal("0")
    assert (s.sources_verified, s.sources_expected) == (0, 4)


def test_check_returns_r6_but_opens_no_gap():
    fc = FakeCore()
    cid = run_to_check(fc)
    findings = fc.check(cid)
    assert [f.rule for f in findings] == ["R4", "R2", "R3", "R5", "R6"]
    assert len(fc.resume_state(cid)[1]) == 4


def test_fake_resolutions_follow_table():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.resolve("G-1", "upload", PRIYA, "h-2", {"path": "data/inbox/x.pdf", **G1_PARAMS})
    assert figures(fc, cid) == (3600, 25684, 12, 1)
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    assert figures(fc, cid) == (8920, 13980, 39, 2)
    fc.resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})
    assert figures(fc, cid) == (13240, 9660, 58, 3)
    fc.resolve("G-4", "approve", LEAD, "h-5", {})
    assert figures(fc, cid) == (22900, 0, 100, 4)
    assert fc.resume_state(cid)[0] == "CHECKING"


def test_fake_resolution_order_independent():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.resolve("G-4", "approve", LEAD, "h-5", {})
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    s = fc.summary(cid)
    assert (s.verified_kgco2e, s.excluded_kgco2e, s.coverage_pct) == (
        Decimal("14980"), Decimal("7820"), Decimal("66"),
    )


def test_reject_resolves_and_keeps_line_excluded():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.resolve("G-3", "reject", LEAD, "h-4", {"reason": "no"})
    phase, gaps = fc.resume_state(cid)
    assert "G-3" not in [g.gap_id for g in gaps]
    s = fc.summary(cid)
    assert (s.verified_kgco2e, s.excluded_kgco2e) == (0, 29184)


def test_pick_b_keeps_b():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0002"})
    s = fc.summary(cid)
    assert (s.verified_kgco2e, s.excluded_kgco2e) == (Decimal("6384"), Decimal("17480"))


def test_fake_role_and_message_guards():
    fc = FakeCore()
    run_to_check(fc)
    with pytest.raises(NotAllowed):
        fc.resolve("G-2", "pick", GUEST, "h-9", {"claim_id": "CL-0003"})
    with pytest.raises(NotAllowed):
        fc.resolve("G-2", "pick", PRIYA, "h-9", {"claim_id": "CL-0003"})
    with pytest.raises(NeedsRoomEvent):
        fc.resolve("G-2", "pick", LEAD, "", {"claim_id": "CL-0003"})
    with pytest.raises(ValueError):
        fc.resolve("G-1", "upload", PRIYA, "h-9", {})
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    with pytest.raises(ValueError) as exc:
        fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    assert str(exc.value) == "gap G-2 is already resolved"


def test_resolve_unknown_gap_and_wrong_action():
    fc = FakeCore()
    run_to_check(fc)
    with pytest.raises(NotFound):
        fc.resolve("G-9", "approve", LEAD, "h-9", {})
    with pytest.raises(ValueError) as exc:
        fc.resolve("G-2", "approve", LEAD, "h-9", {})
    assert str(exc.value) == "gap G-2 has no approve option"


def test_resolve_uses_latest_close():
    fc = FakeCore()
    v1 = run_to_check(fc)
    v2 = run_to_check(fc)
    assert (v1, v2) == ("2026-10-v1", "2026-10-v2")
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    assert "G-2" not in [g.gap_id for g in fc.resume_state(v2)[1]]
    assert "G-2" in [g.gap_id for g in fc.resume_state(v1)[1]]


def test_publish_guards_and_draft_needed():
    fc = FakeCore()
    cid = run_to_check(fc)
    with pytest.raises(NotAllowed):
        fc.publish(cid, PRIYA, "h-9")
    with pytest.raises(ValueError) as exc:
        fc.publish(cid, LEAD, "h-9")
    assert str(exc.value) == "draft the report before publishing"
    fc.draft_report(cid)
    report = fc.publish(cid, LEAD, "h-9")
    assert isinstance(report, Report)
    assert report.approver == "lead"
    assert report.published_at == "2026-11-06T17:00:00Z"
    assert fc.resume_state(cid)[0] == "PUBLISHED"


def test_draft_report_shape():
    fc = FakeCore()
    cid = run_to_check(fc)
    resolve_all(fc)
    report = fc.draft_report(cid)
    assert report.version == 1
    assert report.verified_total_tCO2e == Decimal("22.9")
    assert report.unverified_excluded_tCO2e == Decimal("0")
    assert report.source_coverage == "4 of 4 expected sources verified"
    assert report.gaps == []
    assert report.conflicts == []
    assert [t.tag for t in report.s_tags] == ["S-001", "S-002", "S-003", "S-004"]
    assert [t.file_name for t in report.s_tags] == [
        "hq_electricity_2026-10.pdf", "hq_diesel_2026-10_inv-4471.eml",
        "dc_euwest_cloud_2026-10.json", "warehouse2_electricity_2026-10_actual.pdf",
    ]
    assert report.s_tags[0].approver == "lead"
    assert report.s_tags[0].chat_message_id == "h-5"
    assert report.s_tags[3].approver == "priya"
    assert fc.resume_state(cid)[0] == "DRAFTED"


def test_draft_report_lists_open_gaps_and_conflict():
    fc = FakeCore()
    cid = run_to_check(fc)
    report = fc.draft_report(cid)
    assert report.gaps[1] == {
        "gap_id": "G-2", "title": "HQ October diesel has two invoices 400 L apart", "owner": "lead",
    }
    assert len(report.gaps) == 4
    assert report.conflicts == [report.gaps[1]]
    assert report.s_tags == []


def test_trace():
    fc = FakeCore()
    cid = run_to_check(fc)
    resolve_all(fc)
    fc.draft_report(cid)
    tag = fc.trace(cid, "S-001")
    assert tag.file_name == "hq_electricity_2026-10.pdf"
    assert tag.kgco2e == Decimal("9660")
    with pytest.raises(NotFound) as exc:
        fc.trace(cid, "S-099")
    assert str(exc.value) == "unknown tag: S-099"


def test_fake_threads():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.record_gap_thread(cid, "G-2", "m-4")
    assert fc.gap_for_thread("m-4").gap_id == "G-2"
    fc.record_gap_thread(cid, "G-2", "m-9")
    assert fc.gap_for_thread("m-9") is None
    assert fc.gap_for_thread("m-4").thread_root_message_id == "m-4"
    with pytest.raises(ValueError):
        fc.record_gap_thread(cid, "G-3", "m-4")
    assert fc.gap_for_thread("nope") is None


def test_fake_explain_before_and_after_upload():
    fc = FakeCore()
    cid = run_to_check(fc)
    q = "what is Warehouse-2 October electricity?"
    assert fc.explain(cid, q, LEAD) == (
        "UNKNOWN for warehouse-2, because no VERIFIED ledger rows match, owned by priya"
    )
    fc.resolve("G-1", "upload", PRIYA, "h-2", {"path": "data/inbox/x.pdf", **G1_PARAMS})
    assert fc.explain(cid, q, LEAD) == (
        "Verified ledger facts: CL-0010: warehouse-2 18000 kWh, 3600 kgCO2e, status VERIFIED"
    )


def test_explain_without_site():
    fc = FakeCore()
    cid = run_to_check(fc)
    assert fc.explain(cid, "why is this open?", LEAD) == (
        "UNKNOWN for this close, because no VERIFIED ledger rows match, owned by lead"
    )


def test_hooks_fail_once_delay_keep_open_audit_budget():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.fail["summary"] = NotFound("x")
    with pytest.raises(NotFound):
        fc.summary(cid)
    fc.summary(cid)
    fc.keep_open = {"G-2"}
    fc.resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})
    assert "G-2" in [g.gap_id for g in fc.resume_state(cid)[1]]
    assert fc.summary(cid).verified_kgco2e == 0
    fc.audit = AuditCheck(False, 7, 3)
    assert fc.verify_audit(cid) == AuditCheck(False, 7, 3)
    fc.budget = {"collector": {"used": 9, "limit": 10, "state": "warn"}}
    assert fc.budget_usage(cid) == {"collector": {"used": 9, "limit": 10, "state": "warn"}}


def test_on_resolve_open_adds_gap():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.on_resolve_open = [
        Finding(
            "F-0000000007", "R7", "FINANCE", ["CL-0004"], "hq", "2026-10", "finance",
            "HQ electricity needs finance sign-off", ["Amount: 9660"],
            [Option("approve", "approve", "Sign off")], 2, False,
        )
    ]
    findings = fc.resolve("G-4", "approve", LEAD, "h-5", {})
    gaps = fc.resume_state(cid)[1]
    assert [g.gap_id for g in gaps] == ["G-1", "G-2", "G-3", "G-5"]
    assert gaps[3].owner == "finance"
    assert gaps[3].thread_root_message_id is None
    assert fc.on_resolve_open == []
    assert "F-0000000007" in [f.finding_id for f in findings]


def test_delay_applies():
    fc = FakeCore(delay=0.2)
    start = time.monotonic()
    fc.latest_close()
    assert time.monotonic() - start >= 0.2


def test_calls_record_bound_arguments():
    fc = FakeCore()
    fc.ingest_file("c", "p", LEAD, "h")
    assert fc.calls[-1] == (
        "ingest_file", {"close_id": "c", "path": "p", "actor": LEAD, "chat_message_id": "h", "site": None},
    )


def test_returned_objects_are_copies():
    fc = FakeCore()
    cid = run_to_check(fc)
    fc.resume_state(cid)[1][0].status = "RESOLVED"
    assert fc.resume_state(cid)[1][0].status == "OPEN"
