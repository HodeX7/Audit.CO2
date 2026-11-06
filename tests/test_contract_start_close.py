from __future__ import annotations

import pytest

from carbon_room import config, core
from carbon_room.models import Actor


def test_start_close_validates_the_configured_factor_set_and_locks_it(db, tmp_path, monkeypatch):
    (tmp_path / "sites.yaml").write_text(
        '{"sites":[{"id":"test-site","name":"Test Site","owner":"lead","expected":[]}]}',
        encoding="utf-8",
    )
    (tmp_path / "carbon_room.yaml").write_text(
        '{"factor_sets":{"FS-test":{"DEFRA":"2026"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(core, "connect", lambda: db)
    config.clear_caches()
    actor = Actor("system", "seed", "Seed")
    try:
        close_id = core.start_close("2026-10", ["test-site"], "FS-test", actor, "msg-start")
        event = db.execute("SELECT kind, payload FROM events WHERE close_id=?", (close_id,)).fetchone()
        assert event["kind"] == "factor_set_locked"
        assert '"factor_set":"FS-test"' in event["payload"]
        with pytest.raises(ValueError, match="unknown factor set"):
            core.start_close("2026-11", ["test-site"], "missing", actor, "msg-start")
        with pytest.raises(ValueError, match="valid sites: test-site"):
            core.start_close("2026-11", ["unknown-site"], "FS-test", actor, "msg-start")
    finally:
        config.clear_caches()
