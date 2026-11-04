"""The CLI that agents and teammates call."""

from __future__ import annotations

import json
import shutil

from carbonroom import config
from carbonroom.cli import main


def test_seed_show_export_verify(env, capsys):
    assert main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "11 documents, 10 activities" in out and "later/2026-10_reno_electricity_ELB-RNO-2610.pdf" in out

    assert main(["ledger", "show", "--period", "2026-10"]) == 0
    out = capsys.readouterr().out
    assert "Quantity delivered: 550.0 gal" in out and "Reno Office electricity" in out

    assert main(["ledger", "export", "--period", "2026-10", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["type"] == "cr.ledger.v1" and len(data["activities"]) == 5
    assert data["expected_but_missing"][0]["site_id"] == "reno"

    assert main(["ledger", "verify"]) == 0
    assert "10 activities checked, 0 problem(s)" in capsys.readouterr().out


def test_ingest_json_for_agents(env, capsys):
    main(["seed"])
    capsys.readouterr()
    bill = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    assert main(["ingest", str(bill), "--from", "lena", "--room", "cr-site-reno", "--gap", "GAP-012", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    (r,) = data["results"]
    assert data["type"] == "cr.ingest.v1" and r["status"] == "new" and r["site"] == "reno"
    assert r["activities"][0]["excerpt"] == "Total energy used this period: 15.08 MWh"
    assert main(["ledger", "missing", "--period", "2026-10"]) == 0
    assert "nothing missing" in capsys.readouterr().out


def test_verify_catches_a_changed_document(env, capsys):
    shutil.copy(config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf", env / "upload.pdf")
    main(["seed"])
    main(["ingest", str(env / "upload.pdf"), "--from", "lena"])
    stored = next((config.store_dir()).glob("*.pdf"))
    stored.write_bytes(b"%PDF-1.4 tampered")
    capsys.readouterr()
    assert main(["ledger", "verify"]) == 1
    assert "sha256 changed" in capsys.readouterr().out


def test_extract_dry_run_writes_nothing(env, capsys):
    main(["seed"])
    capsys.readouterr()
    bill = config.seed_dir() / "later" / "2026-10_austin_electricity_ELB-AUS-2610-C.pdf"
    assert main(["extract", str(bill)]) == 0
    assert "OK  electricity 196800 kWh" in capsys.readouterr().out
    main(["ledger", "show", "--period", "2026-10"])
    assert "196,800" not in capsys.readouterr().out


def test_missing_ledger_is_a_clear_error(env, capsys):
    assert main(["ledger", "show", "--period", "2026-10"]) == 1
    assert "carbonroom seed" in capsys.readouterr().err
