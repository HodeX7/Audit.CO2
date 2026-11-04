"""The ledger enforces the honesty rules itself (triggers + helpers)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from carbonroom.ledger import db

TABLES = ["sites", "periods", "source_docs", "activities", "emission_factors", "calculations", "instruments",
          "gaps", "approvals", "events", "expected_documents"]


def _activity(conn, quantity="191300", excerpt="Total energy used this period: 191,300 kWh"):
    db.upsert_site(conn, id="austin", name="Austin Plant", owner_handle="omar", room="cr-site-austin")
    doc, _ = db.add_source_doc(conn, sha256=db.sha256_text(excerpt), path="x.pdf", kind="utility_bill",
                               received_from="omar", room="cr-site-austin")
    act, _ = db.add_activity(conn, site_id="austin", period_id="2026-10", category="electricity",
                             quantity=quantity, unit="kWh", source_doc_id=doc["id"], excerpt=excerpt,
                             excerpt_locator="page=1;line=10", excerpt_sha256=db.sha256_text(excerpt),
                             created_by="test")
    return act


def _one_row_everywhere(conn):
    act = _activity(conn)
    db.upsert_expected_document(conn, site_id="austin", category="electricity", doc_kind="utility_bill")
    db.add_emission_factor(conn, id="F1", set_version="v1", category="electricity", region="ERCT", scope="2_location",
                           factor="0.4", unit="kg CO2e/kWh", source_name="test", source_edition="test")
    db.add_calculation(conn, activity_id=act["id"], factor_id="F1", scope="2_location", co2e_kg="1", code_version="t")
    db.add_instrument(conn, period_id="2026-10", kind="REC", mwh="120", source_doc_id=act["source_doc_id"],
                      created_by="test", excerpt="Quantity retired: 120 MWh")
    db.create_gap(conn, kind="missing_doc", detail="x", created_by="test", site_id="austin")
    db.record_approval(conn, period_id="2026-10", approver_handle="grace", decision="REJECT")


@pytest.mark.parametrize("table", TABLES)
def test_no_table_allows_delete(conn, table):
    _one_row_everywhere(conn)
    assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > 0
    with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
        conn.execute(f"DELETE FROM {table}")


def test_code_contains_no_sql_delete():
    root = Path(__file__).resolve().parents[1] / "carbonroom"
    offenders = [str(p) for p in root.rglob("*.py") if re.search(r"\bDELETE\s+FROM\b", p.read_text(), re.I)]
    assert offenders == []


def test_new_activity_is_unverified_and_evidence_is_immutable(conn):
    act = _activity(conn)
    assert act["status"] == "UNVERIFIED"
    assert act["quantity"] == "191300"
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("UPDATE activities SET quantity = '1' WHERE id = ?", (act["id"],))
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("UPDATE activities SET excerpt = 'x' WHERE id = ?", (act["id"],))


def test_status_transitions(conn):
    act = _activity(conn)
    assert db.set_activity_status(conn, act["id"], "VERIFIED", actor="cr-checker")["status"] == "VERIFIED"
    with pytest.raises(db.LedgerError, match="not allowed"):
        db.set_activity_status(conn, act["id"], "UNVERIFIED", actor="cr-checker")
    with pytest.raises(db.LedgerError, match="needs a reason"):
        db.set_activity_status(conn, act["id"], "FLAGGED", actor="cr-checker")
    flagged = db.set_activity_status(conn, act["id"], "FLAGGED", actor="cr-checker", reason="false done")
    assert flagged["status"] == "FLAGGED" and flagged["status_reason"] == "false done"
    with pytest.raises(db.LedgerError, match="supersede_activity"):
        db.set_activity_status(conn, act["id"], "SUPERSEDED", actor="x")
    actions = [e["action"] for e in db.list_events(conn, ref=act["id"])]
    assert actions.count("activity_status") == 2


def test_supersede_keeps_both_rows_and_is_final(conn):
    old = _activity(conn)
    new = _activity(conn, quantity="196800", excerpt="Total energy used this period: 196,800 kWh")
    with pytest.raises(sqlite3.DatabaseError, match="superseded_by"):
        conn.execute("UPDATE activities SET status='SUPERSEDED' WHERE id=?", (old["id"],))
    done = db.supersede_activity(conn, old["id"], new["id"], actor="cr-checker", reason="corrected bill")
    assert done["status"] == "SUPERSEDED" and done["superseded_by"] == new["id"]
    assert db.get_activity(conn, old["id"]) is not None
    with pytest.raises(sqlite3.DatabaseError, match="final"):
        conn.execute("UPDATE activities SET status='VERIFIED' WHERE id=?", (old["id"],))
    assert [a["id"] for a in db.list_activities(conn, include_superseded=False)] == [new["id"]]


def test_quantities_are_decimal_strings_never_floats(conn):
    with pytest.raises(db.LedgerError, match="floats"):
        db.dec_str(1.5)
    assert db.dec_str("1,892.700") == "1892.7"
    assert db.dec_str("100") == "100"
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("INSERT INTO periods(id) VALUES ('2026-13x')")


def test_gaps_ids_dedupe_and_human_resolution(conn):
    _activity(conn)
    g1, created1 = db.create_gap(conn, kind="missing_doc", detail="Reno bill missing", created_by="cr-checker",
                                 period_id="2026-10", site_id="austin", dedupe_key="k1")
    g1_again, created_again = db.create_gap(conn, kind="missing_doc", detail="dup", created_by="cr-checker",
                                            dedupe_key="k1")
    g2, _ = db.create_gap(conn, kind="conflict", detail="two invoices", created_by="cr-checker", site_id="austin")
    assert (g1["id"], g2["id"]) == ("GAP-001", "GAP-002")
    assert created1 and not created_again and g1_again["id"] == "GAP-001"
    assert g1["owner_handle"] == "omar" and g1["room"] == "cr-site-austin"  # defaults from the site
    with pytest.raises(sqlite3.DatabaseError, match="resolved_by"):
        conn.execute("UPDATE gaps SET status='RESOLVED' WHERE id='GAP-001'")
    with pytest.raises(db.LedgerError):
        db.resolve_gap(conn, "GAP-001", resolution="", resolved_by="omar")
    done = db.resolve_gap(conn, "GAP-001", resolution="uploaded the bill", resolved_by="lena")
    assert done["status"] == "RESOLVED" and done["resolved_by"] == "lena"
    with pytest.raises(db.LedgerError, match="already"):
        db.resolve_gap(conn, "GAP-001", resolution="again", resolved_by="lena")


def test_period_closes_only_after_recorded_approval(conn):
    db.ensure_period(conn, "2026-10")
    with pytest.raises(db.LedgerError, match="APPROVE"):
        db.close_period(conn, "2026-10", approved_by="grace", actor="cr-reporter")
    db.record_approval(conn, period_id="2026-10", approver_handle="omar", decision="APPROVE")
    with pytest.raises(db.LedgerError, match="APPROVE"):  # approval by someone else doesn't count
        db.close_period(conn, "2026-10", approved_by="grace", actor="cr-reporter")
    db.record_approval(conn, period_id="2026-10", approver_handle="grace", decision="APPROVE", report_sha256="ab")
    assert db.close_period(conn, "2026-10", approved_by="grace", actor="cr-reporter")["status"] == "CLOSED"
    with pytest.raises(db.LedgerError, match="locked"):
        db.set_period_factor_set(conn, "2026-10", "v2", actor="x")


def test_events_and_approvals_are_append_only(conn):
    db.ensure_period(conn, "2026-10")
    db.record_approval(conn, period_id="2026-10", approver_handle="grace", decision="REJECT", note="no")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE events SET actor='someone'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE approvals SET decision='APPROVE'")


def test_calculations_append_only(conn):
    act = _activity(conn)
    db.add_emission_factor(conn, id="F1", set_version="v1", category="electricity", region="ERCT", scope="2_location",
                           factor="0.4", unit="kg CO2e/kWh", source_name="test", source_edition="test")
    calc = db.add_calculation(conn, activity_id=act["id"], factor_id="F1", scope="2_location", co2e_kg="76520",
                              code_version="test")
    assert calc["co2e_kg"] == "76520"
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE calculations SET co2e_kg='1'")
