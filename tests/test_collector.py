"""Collector: hashing, duplicate skipping, the inbox hand-off folder, evidence storage."""

from __future__ import annotations

import json
import shutil

from carbonroom import config
from carbonroom.ingest import collector, pipeline, rules
from carbonroom.ingest.extract import read_pages
from carbonroom.ledger import db


def _reno_oct():
    return config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"


def test_duplicates_are_skipped_by_hash_even_under_another_name(sites, env):
    first = pipeline.ingest_file(sites, _reno_oct(), received_from="lena", room="cr-site-reno")
    renamed = env / "copy-of-reno-bill.pdf"
    shutil.copy(_reno_oct(), renamed)
    second = pipeline.ingest_file(sites, renamed, received_from="lena")
    assert first["status"] == "new" and second["status"] == "duplicate"
    assert second["doc_id"] == first["doc_id"]
    assert len(db.list_source_docs(sites)) == 1
    assert len(db.list_activities(sites)) == 1


def test_inbox_handoff_folder_with_sidecar(sites, env):
    room_dir = config.inbox_dir() / "cr-site-reno"
    room_dir.mkdir(parents=True)
    dropped = room_dir / "reno-october.pdf"
    shutil.copy(_reno_oct(), dropped)
    (room_dir / "reno-october.pdf.meta.json").write_text(json.dumps(
        {"received_from": "lena", "thread_id": "th-42", "message_id": "m-7", "gap_id": "GAP-012"}))
    results = pipeline.ingest_paths(sites, [config.inbox_dir()], move_processed=True)
    (r,) = results
    assert r["status"] == "new" and r["room"] == "cr-site-reno" and r["received_from"] == "lena"
    doc = db.get_source_doc(sites, r["doc_id"])
    assert doc["meta"]["thread_id"] == "th-42" and doc["meta"]["gap_id"] == "GAP-012"
    # evidence is copied to a content-addressed store, so moving/deleting the upload can't lose it
    assert doc["path"].endswith(f"store/{doc['sha256']}.pdf")
    assert not dropped.exists()
    assert (config.inbox_dir() / "_processed" / "cr-site-reno" / "reno-october.pdf").exists()
    assert pipeline.ingest_paths(sites, [config.inbox_dir()]) == []  # _processed is not re-scanned


def test_seed_files_are_referenced_in_place(sites):
    r = pipeline.ingest_file(sites, _reno_oct(), received_from="lena")
    assert db.get_source_doc(sites, r["doc_id"])["path"].endswith("seed/later/2026-10_reno_electricity_ELB-RNO-2610.pdf")


def test_unreadable_file_becomes_a_gap_not_a_number(sites, env):
    photo = config.inbox_dir() / "cr-site-reno" / "bill-photo.png"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"\x89PNG\r\n\x1a\nnot really an image")
    (r,) = pipeline.ingest_paths(sites, [photo], received_from="lena")
    assert r["activities"] == [] and r["kind"] == "other"
    (gap,) = r["gaps"]
    assert gap["kind"] == "unverified_claim" and gap["owner"] == "lena" and gap["room"] == "cr-site-reno"
    assert "no readable text" in gap["detail"]


def test_kind_rules():
    seed = config.seed_dir()
    def kind(name):
        folder = "later" if "2610-C" in name or "RNO-2610" in name else "docs"
        return rules.classify(read_pages(seed / folder / name))
    assert kind("2026-10_austin_electricity_ELB-AUS-2610.pdf") == "utility_bill"
    assert kind("2026-10_austin_gas_GAS-AUS-2610.pdf") == "utility_bill"
    assert kind("2026-10_austin_diesel_INV-204.pdf") == "fuel_invoice"
    assert kind("2026-10_nimbus_cloud_NC-2610.pdf") == "cloud_invoice"
    assert kind("2026-10_rec_REC-WECC-2023-55120.pdf") == "rec_certificate"
    assert rules.classify(["Dear customer, thanks for your order."]) == "other"


def test_iter_files_skips_sidecars_and_hidden(env):
    folder = env / "drop"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"%PDF")
    (folder / "a.pdf.meta.json").write_text("{}")
    (folder / ".DS_Store").write_bytes(b"x")
    (folder / "notes.docx").write_bytes(b"x")
    assert [p.name for p in collector.iter_files(folder)] == ["a.pdf"]
