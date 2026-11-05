"""Every demo trap from contract 5.6 shows up in the ledger exactly as the checker needs it."""

from __future__ import annotations

from decimal import Decimal

from carbonroom import config
from carbonroom.ingest import extract, pipeline, seedgen
from carbonroom.ingest.evidence import evidence_status
from carbonroom.ingest.hashing import excerpt_sha256, sha256_file
from carbonroom.ingest.seed import run_seed
from carbonroom.ledger import db

LATER = "later"


def _acts(conn, period, site=None, category=None):
    return db.list_activities(conn, period_id=period, site_id=site, category=category, include_superseded=False)


def test_seed_loads_everything_unverified_with_proof(seeded):
    docs = db.list_source_docs(seeded)
    acts = db.list_activities(seeded)
    assert len(docs) == 11 and len(acts) == 10 and len(db.list_instruments(seeded)) == 1
    assert db.list_gaps(seeded) == []
    for act in acts:
        assert act["status"] == "UNVERIFIED"
        doc = db.get_source_doc(seeded, act["source_doc_id"])
        assert sha256_file(extract.resolve_doc_path(doc["path"])) == doc["sha256"]
        assert act["excerpt_sha256"] == excerpt_sha256(act["excerpt"])
        assert extract.excerpt_in_document(doc["path"], act["excerpt"], extract.locator_page(act["excerpt_locator"]))
        assert db.dec(act["quantity"]) in extract.numbers_in(act["excerpt"]) or act["extra"]["conversion"] != "none"
    assert {p["id"] for p in db.list_periods(seeded)} == {"2026-09", "2026-10"}


def test_trap1_missing_reno_october_bill(seeded):
    assert _acts(seeded, "2026-10", "reno") == []
    assert db.expected_but_missing(seeded, "2026-10") == [{
        "site_id": "reno", "site_name": "Reno Office", "category": "electricity", "doc_kind": "utility_bill",
        "period_id": "2026-10", "owner_handle": "lena", "room": "cr-site-reno"}]
    assert db.expected_but_missing(seeded, "2026-09") == []
    # Lena drops the bill in the thread -> it lands as a normal UNVERIFIED row
    r = pipeline.ingest_file(seeded, config.seed_dir() / LATER / "2026-10_reno_electricity_ELB-RNO-2610.pdf",
                             received_from="lena", room="cr-site-reno", meta={"gap_id": "GAP-012"})
    assert r["activities"][0]["quantity"] == "15080"
    assert db.expected_but_missing(seeded, "2026-10") == []


def test_trap2_conflicting_diesel_invoices_are_both_kept(seeded):
    diesel = _acts(seeded, "2026-10", "austin", "diesel")
    assert sorted(Decimal(a["quantity"]) for a in diesel) == [Decimal(500), Decimal(550)]
    assert {a["extra"]["delivery_ref"] for a in diesel} == {"DLV-7731"}
    assert {a["extra"]["doc_ref"] for a in diesel} == {"INV-204", "INV-204B"}
    assert len({a["source_doc_id"] for a in diesel}) == 2
    assert db.list_gaps(seeded, kind="conflict") == []  # flagging it is the checker's job


def test_trap4_false_done_corrected_bill(seeded):
    (original,) = _acts(seeded, "2026-10", "austin", "electricity")
    assert original["quantity"] == "191300"
    db.set_activity_status(seeded, original["id"], "VERIFIED", actor="cr-checker")  # the checker passed it
    assert evidence_status(seeded, original["id"])["ok"]

    r = pipeline.ingest_file(seeded, config.seed_dir() / LATER / "2026-10_austin_electricity_ELB-AUS-2610-C.pdf",
                             received_from="omar", room="cr-site-austin")
    (new,) = r["activities"]
    assert new["quantity"] == "196800" and new["replaces_activity_ids"] == [original["id"]]
    old_doc = db.get_source_doc(seeded, original["source_doc_id"])
    assert old_doc["superseded_by"] == r["doc_id"]
    # ingestion does not touch the verified row: the checker must notice and reopen it
    assert db.get_activity(seeded, original["id"])["status"] == "VERIFIED"
    status = evidence_status(seeded, original["id"])
    assert not status["ok"] and status["source_superseded"] and not status["excerpt_in_current_doc"]
    assert status["replacement_activity_ids"] == [new["id"]]
    # what the checker does next, using the db helpers
    db.set_activity_status(seeded, original["id"], "FLAGGED", actor="cr-checker", reason="false done")
    db.supersede_activity(seeded, original["id"], new["id"], actor="cr-checker", reason="corrected bill")
    assert [a["id"] for a in _acts(seeded, "2026-10", "austin", "electricity")] == [new["id"]]


def test_trap5_gas_outlier(seeded):
    (sep,) = _acts(seeded, "2026-09", "austin", "natural_gas")
    (oct_,) = _acts(seeded, "2026-10", "austin", "natural_gas")
    change = (Decimal(oct_["quantity"]) / Decimal(sep["quantity"]) - 1) * 100
    assert change.quantize(Decimal("0.1")) == Decimal("60.4")


def test_trap6_data_centre_line_and_low_quality_rec(seeded):
    (cloud,) = _acts(seeded, "2026-10", "nimbus-cloud", "cloud_compute")
    assert (cloud["quantity"], cloud["unit"]) == ("38200", "kWh")
    assert cloud["excerpt_locator"].startswith("page=2")
    assert (cloud["extra"]["pue"], cloud["extra"]["wue_l_per_kwh"]) == ("1.35", "0.42")
    assert cloud["extra"]["evidence"]["pue"]["locator"].startswith("page=2")
    (rec,) = db.list_instruments(seeded, period_id="2026-10")
    site = db.get_site(seeded, rec["site_id"])
    assert (rec["kind"], rec["mwh"], rec["vintage"]) == ("REC", "120", "2023")
    assert rec["certificate_id"] == "REC-WECC-2023-55120"
    assert rec["region"] == "WECC Northwest (Oregon)" and site["grid_subregion"] == "SRVC" and site["kind"] == "cloud"
    assert rec["quality_flags"] == []  # flagging is the checker's job


def test_unit_normalization_keeps_the_original(seeded):
    (reno,) = _acts(seeded, "2026-09", "reno", "electricity")
    assert (reno["quantity"], reno["unit"]) == ("14620", "kWh")
    assert (reno["extra"]["original_quantity"], reno["extra"]["original_unit"]) == ("14.62", "MWh")
    (diesel,) = _acts(seeded, "2026-09", "austin", "diesel")
    assert (diesel["quantity"], diesel["unit"], diesel["extra"]["original_unit"]) == ("499.998", "gal", "L")


def _snapshot(conn):
    tables = ["source_docs", "activities", "instruments", "gaps", "periods", "sites"]
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY id")] for t in tables}


def test_ingest_is_idempotent(seeded):
    before = _snapshot(seeded)
    results = pipeline.ingest_paths(seeded, [config.seed_dir() / "docs"])
    assert {r["status"] for r in results} == {"duplicate"}
    assert _snapshot(seeded) == before


def test_seed_is_reproducible(env):
    first = run_seed(env / "a.db")
    second = run_seed(env / "b.db")
    ids = lambda s: [a["id"] for r in s["results"] for a in r["activities"]]  # noqa: E731
    assert ids(first) == ids(second) and len(ids(first)) == 10


def test_seed_pdfs_are_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    seedgen.generate(a)
    seedgen.generate(b)
    for path in a.rglob("*.pdf"):
        assert sha256_file(path) == sha256_file(b / path.relative_to(a))
    every_page = [page for d in seedgen.seed_documents() for page in d.pages]
    assert every_page and all(isinstance(page, list) for page in every_page)


def test_every_seed_page_says_fictional():
    for path in sorted(config.repo_root().joinpath("data", "seed").rglob("*.pdf")):
        for page in extract.read_pages(path):
            assert "FICTIONAL DOCUMENT" in page, path


def test_committed_cache_covers_every_seed_document():
    from carbonroom.ingest.seed import manifest

    seed = config.repo_root() / "data" / "seed"
    for entry in manifest(seed):
        sha = sha256_file(seed / entry["path"])
        assert (seed / "extractions" / f"{sha}.json").exists(), entry["path"]


def test_rows_carry_the_names_the_calculator_and_checker_read(seeded):
    """Richa's conflict rule groups by extra.delivery_id; her data-centre line reads extra.pue and extra.wue."""
    diesel = db.list_activities(seeded, period_id="2026-10", category="diesel")
    assert {a["extra"]["delivery_id"] for a in diesel} == {"DLV-7731"}
    assert {a["extra"]["delivery_id"] for a in diesel} == {a["extra"]["delivery_ref"] for a in diesel}
    assert len({a["quantity"] for a in diesel}) == 2  # so the conflict fires
    cloud = db.list_activities(seeded, period_id="2026-10", category="cloud_compute")[0]["extra"]
    assert (cloud["pue"], cloud["wue"], cloud["wue_l_per_kwh"]) == ("1.35", "0.42", "0.42")
