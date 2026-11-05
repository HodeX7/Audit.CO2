"""Shared fixtures: every test gets its own data folder and ledger file (no network, no API key)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True, scope="session")
def _ignore_developer_dotenv():
    """Tests never read the developer's .env (real keys, real model), whatever order they run in."""
    from carbonroom import config

    config._ENV_LOADED = True
    os.environ["CR_GRAPH"] = "off"  # no Neo4j in tests unless a test opts in with a fake store


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A private copy of data/seed plus an empty inbox; CR_* variables point at it."""
    data = tmp_path / "data"
    shutil.copytree(REPO / "data" / "seed", data / "seed")
    (data / "inbox").mkdir(parents=True)
    monkeypatch.setenv("CR_DATA_DIR", str(data))
    monkeypatch.setenv("CR_DB_PATH", str(tmp_path / "carbonroom.db"))
    monkeypatch.setenv("CR_NOW", "2026-11-03T18:31:00Z")
    monkeypatch.setenv("CR_PROPOSER", "auto")
    for key in ("NVIDIA_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "CR_FACTOR_SET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def conn(env):
    from carbonroom.ledger import db

    connection = db.connect(env / "carbonroom.db")
    yield connection
    connection.close()


@pytest.fixture
def seeded(env):
    from carbonroom.ingest.seed import run_seed
    from carbonroom.ledger import db

    run_seed(env / "carbonroom.db")
    connection = db.connect(env / "carbonroom.db")
    yield connection
    connection.close()


@pytest.fixture
def sites(conn):
    """Sites only (no documents), for extraction tests."""
    from carbonroom import config
    from carbonroom.ingest.seed import load_sites

    load_sites(conn, config.seed_dir() / "sites.json")
    return conn


@pytest.fixture
def db(tmp_path):
    """Isolated contract-ledger database for tests that use the shared API."""
    from carbon_room.ledger import connect, init_db

    conn = connect(tmp_path / "carbon_room.db")
    init_db(conn)
    yield conn
    conn.close()
