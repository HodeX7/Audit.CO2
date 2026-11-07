"""P2's offline acceptance flow also works when extraction uses P1 replay entries."""

from hashlib import sha256
from pathlib import Path
from shutil import copytree

from carbon_room import collect
from carbon_room.actors import CALCULATOR
from carbon_room.calc import run as calc_run
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger
from carbon_room.sources import cache
from carbon_room.sources.readers import read

ROOT = Path(__file__).resolve().parents[1]


def test_seed_replay_requires_no_network_or_model(factor_db, close_id, monkeypatch, tmp_path):
    copytree(ROOT / "data/seed", tmp_path / "data/seed")
    monkeypatch.chdir(tmp_path)
    for path in (tmp_path / "data/seed").glob("*/*"):
        kind, pages = read(path)
        if kind == "cloud_invoice":
            continue  # P1 parses structured cloud JSON deterministically.
        candidate = collect._candidate(pages)
        assert candidate is not None
        cache.save(sha256(path.read_bytes()).hexdigest(), [candidate])
    monkeypatch.setattr(collect, "_mode", lambda: "replay")
    ingested = collect.ingest(factor_db, close_id, CALCULATOR)
    assert ingested.failed_sources == []
    assert len(ingested.claims_created) == 9
    calc_run.calculate(factor_db, close_id)
    check_run.check(factor_db, close_id)
    assert {gap.rule for gap in ledger.get_gaps(factor_db, close_id, status="OPEN")} == {"R2", "R3", "R4", "R5"}
