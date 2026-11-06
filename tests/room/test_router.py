"""Router (SPEC-11 section 6)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fakes.fake_core import FakeCore

from carbon_room.models import Actor
from carbon_room.room.router import GapAction, NoMatch, find_gap, match_reply

LEAD = Actor("human", "lead", "Sustainability Lead", "lead")
COLLECTOR = Actor("agent", "collector", "Collector")


def _gaps():
    fc = FakeCore()
    cid = fc.start_close("2026-10", ["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "h-1")
    fc.ingest(cid, COLLECTOR)
    fc.calculate(cid)
    fc.check(cid)
    return fc.resume_state(cid)[1]


G1, G2, G3, G4 = _gaps()
G1_PARAMS = {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}


def test_pick_a_in_diesel_gap_gives_option_a_params():
    assert match_reply(G2, "Pick a", False) == GapAction(G2, G2.options[0], {"claim_id": "CL-0003"}, None)


@pytest.mark.parametrize("t", ["pick B", "PICK OPTION b", "pick b!"])
def test_pick_b_variants(t):
    r = match_reply(G2, t, False)
    assert r.option.key == "pick B"
    assert r.payload == {"claim_id": "CL-0002"}


def test_hello_gives_unknown_reply():
    assert match_reply(G2, "hello", False) == NoMatch(G2, "unknown_reply")


def test_empty_text_no_attachment():
    assert match_reply(G2, "", False) == NoMatch(G2, "unknown_reply")


def test_approved_counts_as_approve():
    r = match_reply(G4, "Approved.", False)
    assert r.option.action == "approve"
    assert r.payload == {}


def test_reject_reason_in_payload():
    assert match_reply(G3, "Reject: wrong site", False).payload == {"reason": "wrong site"}
    assert match_reply(G3, "reject", False).payload == {}


def test_params_are_copied():
    a = match_reply(G3, "approve", False)
    a.payload["x"] = 1
    assert G3.options[0].params == {"use_factor_id": "EMBER-2025-IE"}


def test_attachment_counts_as_upload():
    expected = GapAction(G1, G1.options[0], G1_PARAMS, None)
    assert match_reply(G1, "", True) == expected
    assert match_reply(G1, "thanks", True) == expected


def test_attachment_on_gap_without_upload_is_ignored():
    assert match_reply(G4, "approve", True).option.action == "approve"
    assert match_reply(G4, "", True) == NoMatch(G4, "unknown_reply")


def test_upload_typed_name():
    assert match_reply(G1, "upload Bill_Oct.pdf", False).filename == "Bill_Oct.pdf"
    assert match_reply(G1, "upload", False).filename is None


def test_upload_text_on_gap_without_upload():
    assert match_reply(G2, "upload x.pdf", False) == NoMatch(G2, "unknown_reply")


def test_resolved_and_optionless():
    r = replace(G2, status="RESOLVED")
    assert match_reply(r, "pick a", False) == NoMatch(r, "gap_resolved")
    o = replace(G2, options=[])
    assert match_reply(o, "pick a", False) == NoMatch(o, "no_options")


def test_find_gap_case_insensitive():
    assert find_gap([G1, G2], "g-2") is G2
    assert find_gap([G1, G2], "G-9") is None
