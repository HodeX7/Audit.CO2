"""Background batch run: parallel, deterministic, one final summary, safe for parallel LangGraph nodes."""

from __future__ import annotations

import json
import shutil
import threading
import time

import pytest

from carbonroom import config
from carbonroom.cli import main
from carbonroom.ingest import batch, extract, pipeline
from carbonroom.ledger import db


def _sites_only(path):
    from carbonroom.ingest.seed import load_sites

    conn = db.connect(path)
    load_sites(conn, config.seed_dir() / "sites.json")
    return conn


def test_seed_documents_as_one_background_run(env):
    conn = _sites_only(env / "a.db")
    summary = batch.run_batch(conn, [config.seed_dir() / "docs"], workers=4, run_id="RUN-test")
    assert summary["type"] == "cr.batch.v1" and summary["run_id"] == "RUN-test"
    assert (summary["new"], summary["duplicates"], summary["failed"]) == (11, 0, 0)
    assert (summary["activities_count"], summary["instruments_count"], len(summary["gaps"])) == (10, 1, 0)
    assert [m["site_id"] for m in summary["expected_but_missing"]["2026-10"]] == ["reno"]
    assert "Still missing: Reno Office electricity 2026-10 (@lena)" in summary["summary_text"]
    assert all(d["meta"]["run_id"] == "RUN-test" for d in db.list_source_docs(conn))
    assert batch.get_run(conn, "RUN-test")["summary_text"] == summary["summary_text"]
    assert [r["run_id"] for r in batch.list_runs(conn)] == ["RUN-test"]


def test_same_ids_and_gap_numbers_with_1_or_8_workers(env):
    folder = env / "drop"
    shutil.copytree(config.seed_dir() / "docs", folder)
    (folder / "photo-of-bill.png").write_bytes(b"\x89PNG not really")  # becomes a gap
    (folder / "copy-of-INV-204.pdf").write_bytes((folder / "2026-10_austin_diesel_INV-204.pdf").read_bytes())
    outcomes = []
    for workers, name in ((1, "one.db"), (8, "eight.db")):
        conn = _sites_only(env / name)
        summary = batch.run_batch(conn, [folder], workers=workers, received_from="omar")
        outcomes.append((
            sorted(a["id"] for a in db.list_activities(conn)),
            [(g["id"], g["detail"]) for g in db.list_gaps(conn)],
            summary["duplicates"],
        ))
    assert outcomes[0] == outcomes[1]
    assert outcomes[0][2] == 1 and len(outcomes[0][1]) == 1  # the copy is a duplicate; the photo is a gap


def test_preparation_really_runs_in_parallel(env, monkeypatch):
    real_propose = extract.propose
    live, peak, lock = [0], [0], threading.Lock()

    def slow_propose(*args, **kwargs):  # stands in for a slow model call
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.15)
        try:
            return real_propose(*args, **kwargs)
        finally:
            with lock:
                live[0] -= 1

    monkeypatch.setattr(extract, "propose", slow_propose)
    conn = _sites_only(env / "p.db")
    batch.run_batch(conn, [config.seed_dir() / "docs"], workers=4)
    assert 1 < peak[0] <= 4


def test_one_bad_file_does_not_stop_the_run(env, monkeypatch):
    real_read = extract.read_pages

    def flaky(path):
        if "GAS-AUS-2610" in str(path):
            raise RuntimeError("disk hiccup")
        return real_read(path)

    monkeypatch.setattr(extract, "read_pages", flaky)
    conn = _sites_only(env / "f.db")
    summary = batch.run_batch(conn, [config.seed_dir() / "docs"], workers=3)
    assert summary["new"] == 10 and summary["failed"] == 1
    assert "disk hiccup" in summary["errors"][0]["error"] and "1 failed" in summary["summary_text"]
    assert any(e["action"] == "ingest_error" for e in db.list_events(conn))
    # nothing half-written: running again picks up the file that failed
    monkeypatch.setattr(extract, "read_pages", real_read)
    again = batch.run_batch(conn, [config.seed_dir() / "docs"], workers=3)
    assert (again["new"], again["duplicates"]) == (1, 10)


def test_parallel_langgraph_nodes_share_one_ledger(env):
    db_path = env / "shared.db"
    _sites_only(db_path).close()
    docs = sorted((config.seed_dir() / "docs").glob("*.pdf"))
    later = sorted((config.seed_dir() / "later").glob("*.pdf"))
    groups = [docs[0:4], docs[4:8], docs[8:] + later]  # e.g. one Send() per collector
    outputs, failures = [], []

    def node(files):
        try:
            outputs.append(batch.collect_node({"files": files, "db_path": str(db_path), "workers": 2}))
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)

    threads = [threading.Thread(target=node, args=(g,)) for g in groups]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert failures == []
    summaries = [s for out in outputs for s in out["ingest_summaries"]]
    assert len(summaries) == 3 and sum(s["new"] for s in summaries) == 13
    conn = db.connect(db_path)
    assert len(db.list_source_docs(conn)) == 13
    gap_ids = [g["id"] for g in db.list_gaps(conn)]
    assert len(gap_ids) == len(set(gap_ids))


def test_cli_summary_and_runs(env, capsys):
    main(["init"])
    _sites_only(env / "carbonroom.db").close()
    capsys.readouterr()
    assert main(["ingest", str(config.seed_dir() / "docs"), "--workers", "4", "--summary", "--run-id", "RUN-cli"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("RUN-cli: Collected 11 new documents") and "Reno Office" in out
    bill = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    assert main(["ingest", str(bill), "--from", "lena", "--summary", "--json", "--period", "2026-10"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["type"] == "cr.batch.v1" and data["expected_but_missing"]["2026-10"] == []
    assert main(["ledger", "runs"]) == 0
    assert "RUN-cli" in capsys.readouterr().out
    assert main(["ledger", "runs", "--id", "RUN-cli", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["new"] == 11
    assert main(["ledger", "runs", "--id", "RUN-nope"]) == 1


def test_plain_ingest_is_unchanged_without_batch_flags(env, capsys):
    main(["seed"])
    capsys.readouterr()
    bill = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    assert main(["ingest", str(bill), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["type"] == "cr.ingest.v1" and "summary" not in data
