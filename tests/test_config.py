from __future__ import annotations

from carbon_room import config


def test_expected_sources_are_site_driven():
    config.clear_caches()
    assert len(config.expected_sources("2026-10")) == 4


def test_config_directory_override_supports_renamed_sites(tmp_path, monkeypatch):
    (tmp_path / "sites.yaml").write_text(
        '{"sites":[{"id":"new-site","owner":"owner","expected":[{"kind":"utility_pdf","activity":"electricity_kwh"}]}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(tmp_path))
    config.clear_caches()
    assert config.expected_sources("2026-10") == [("new-site", "utility_pdf", "electricity_kwh")]
    assert config.site_owner("new-site") == "owner"
    config.clear_caches()
