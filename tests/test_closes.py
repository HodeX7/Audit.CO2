"""A close of a month: boundary and factor set locked at the start, phase stored in the ledger, versions."""

from __future__ import annotations

import sqlite3

import pytest

from carbonroom.cli import main
from carbonroom.ledger import db
from carbonroom.ledger import graph as ledger_graph


@pytest.fixture
def seeded(env):
    assert main(["seed"]) == 0
    conn = db.connect()
    yield conn
    conn.close()


def test_start_close_locks_the_boundary_and_the_factor_set(seeded):
    close = db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024", sites=["reno", "austin"],
                           chat_message_id="mm-1")
    assert close["id"] == "CLOSE-2026-10-v1"
    assert (close["sites"], close["factor_set"], close["phase"]) == (["austin", "reno"], "egrid-2024", "OPEN")
    assert db.get_period(seeded, "2026-10")["factor_set_version"] == "egrid-2024"
    with pytest.raises(db.LedgerError, match="locked by this month's open close"):
        db.set_period_factor_set(seeded, "2026-10", "egrid-2025", actor="cr-calc")
    with pytest.raises(sqlite3.IntegrityError, match="locked"):
        seeded.execute("UPDATE closes SET sites_json = '[\"austin\"]' WHERE id = ?", (close["id"],))
    event = seeded.execute("SELECT * FROM events WHERE action = 'close_started'").fetchone()
    assert (event["actor"], event["chat_message_id"]) == ("maya", "mm-1")


def test_one_open_close_per_month_and_resume_finds_it(seeded):
    close = db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024")
    with pytest.raises(db.LedgerError, match="resume it"):
        db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024")
    with pytest.raises(sqlite3.IntegrityError, match="open close"):
        seeded.execute("INSERT INTO closes(id, period_id, version, sites_json, factor_set, started_by, started_at) "
                       "VALUES ('CLOSE-2026-10-v9', '2026-10', 9, '[]', 'x', 'x', 'x')")
    assert db.get_open_close(seeded, "2026-10")["id"] == close["id"]


def test_phases_follow_the_close_flow_and_repeat_safely(seeded):
    close = db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024")
    with pytest.raises(db.LedgerError, match="not allowed"):
        db.set_close_phase(seeded, close["id"], "DRAFTED", actor="cr-carbon-room")
    for phase in ("COLLECTING", "COLLECTING", "CALCULATING", "CHECKING", "AWAITING_HUMANS", "RECHECKING",
                  "AWAITING_HUMANS", "RECHECKING", "DRAFTED"):
        close = db.set_close_phase(seeded, close["id"], phase, actor="cr-carbon-room")
    assert close["phase"] == "DRAFTED"
    with pytest.raises(db.LedgerError, match="publish_close"):
        db.set_close_phase(seeded, close["id"], "PUBLISHED", actor="cr-carbon-room")
    moves = [db.row_to_dict(r)["detail"]["to"] for r in
             seeded.execute("SELECT * FROM events WHERE action = 'close_phase' ORDER BY id")]
    assert moves == ["COLLECTING", "CALCULATING", "CHECKING", "AWAITING_HUMANS", "RECHECKING", "AWAITING_HUMANS",
                     "RECHECKING", "DRAFTED"]  # the repeated COLLECTING was a no-op


def test_a_new_version_starts_only_after_publishing_and_keeps_the_factor_set(seeded):
    close = db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024")
    for phase in ("COLLECTING", "CALCULATING", "CHECKING", "DRAFTED"):
        db.set_close_phase(seeded, close["id"], phase, actor="cr-carbon-room")
    db.record_approval(seeded, period_id="2026-10", approver_handle="maya", decision="APPROVE", chat_message_id="m")
    db.publish_close(seeded, close["id"], published_by="maya", chat_message_id="mm-pub")
    with pytest.raises(db.LedgerError, match="same set"):
        db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2025")
    v2 = db.start_close(seeded, "2026-10", actor="maya")
    assert (v2["id"], v2["version"], v2["factor_set"]) == ("CLOSE-2026-10-v2", 2, "egrid-2024")
    assert [c["version"] for c in db.list_closes(seeded, "2026-10")] == [1, 2]


def test_bad_boundaries_and_missing_factor_sets_are_refused(seeded):
    with pytest.raises(db.LedgerError, match="unknown site"):
        db.start_close(seeded, "2026-10", actor="maya", factor_set="x", sites=["mars-base"])
    with pytest.raises(db.LedgerError, match="factor set"):
        db.start_close(seeded, "2026-10", actor="maya")


def test_missing_evidence_counts_only_inside_the_boundary(seeded):
    assert {m["site_id"] for m in db.expected_but_missing(seeded, "2026-10")} == {"reno"}
    db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024", sites=["austin", "nimbus-cloud"])
    assert db.expected_but_missing(seeded, "2026-10") == []
    assert {m["site_id"] for m in db.expected_but_missing(seeded, "2026-10", sites=["reno"])} == {"reno"}


def test_the_close_is_in_the_graph_and_the_export(seeded):
    db.start_close(seeded, "2026-10", actor="maya", factor_set="egrid-2024", sites=["austin", "reno"])
    links = {(e["rel"], f"{e['dst_type']}:{e['dst_id']}")
             for e in ledger_graph.edges(seeded, "close", "CLOSE-2026-10-v1", direction="out")}
    assert {("for_period", "period:2026-10"), ("covers", "site:austin"), ("covers", "site:reno"),
            ("started_by", "person:maya")} <= links
    assert ledger_graph.resolve(seeded, "CLOSE-2026-10-v1") == ("close", "CLOSE-2026-10-v1")
    assert [c["id"] for c in db.export_period(seeded, "2026-10")["closes"]] == ["CLOSE-2026-10-v1"]
