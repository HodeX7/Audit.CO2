"""Shared fixtures for the room tests."""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest
from fakes.fake_core import FakeCore
from fakes.fake_room import FakeRoom

from carbon_room import config
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.ports import Context

FIXTURES = Path(__file__).parent / "fixtures"
REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def people_config(tmp_path, monkeypatch):
    target = tmp_path / "config"
    target.mkdir()
    shutil.copy(REPO_CONFIG / "sites.yaml", target / "sites.yaml")
    shutil.copy(FIXTURES / "people.yaml", target / "people.yaml")
    shutil.copy(FIXTURES / "carbon_room.yaml", target / "carbon_room.yaml")
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(target))
    config.clear_caches()
    yield target
    config.clear_caches()


@pytest.fixture
def fake_core():
    return FakeCore()


@pytest.fixture
def fake_room():
    return FakeRoom()


@pytest.fixture
def core_executor():
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="core")
    yield executor
    executor.shutdown(wait=True)


@pytest.fixture
def ctx(fake_core, fake_room, core_executor):
    return Context(
        core=AsyncCore(fake_core, core_executor),
        room=fake_room,
        display=lambda pid: f"@{pid}",
        today=lambda: date(2026, 11, 5),
    )
