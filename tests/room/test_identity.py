"""Identity: Switch sender to Actor, display names and people.yaml checks."""

from __future__ import annotations

import shutil
from pathlib import Path

from carbon_room import config
from carbon_room.models import Actor
from carbon_room.room import identity

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def _tmp_config(tmp_path, monkeypatch, people_text=None):
    target = tmp_path / "cfg"
    target.mkdir()
    shutil.copy(REPO_CONFIG / "sites.yaml", target / "sites.yaml")
    if people_text is not None:
        (target / "people.yaml").write_text(people_text, encoding="utf-8")
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(target))
    config.clear_caches()


def test_known_person_maps_to_role(people_config):
    assert identity.actor_for("@switch-user-priya:test", "priya") == Actor(
        "human", "priya", "Priya", "site_manager"
    )


def test_lead_maps_to_lead(people_config):
    assert identity.actor_for("@switch-user-lead:test", "whatever") == Actor(
        "human", "lead", "Sustainability Lead", "lead"
    )


def test_unknown_sender_is_guest(people_config):
    assert identity.actor_for("@switch-user-zed:test", "zed") == Actor(
        "human", "guest:@switch-user-zed:test", "zed", None
    )
    assert identity.actor_for("@x:test", "") == Actor("human", "guest:@x:test", "@x:test", None)


def test_agent_sender_maps_to_agent(people_config):
    assert identity.actor_for("agent-wd", "watchdog", agent_ids={"agent-wd": "watchdog"}) == Actor(
        "agent", "watchdog", "Watchdog", None
    )


def test_person_wins_over_agent_map(people_config):
    actor = identity.actor_for(
        "@switch-user-lead:test", "lead", agent_ids={"@switch-user-lead:test": "watchdog"}
    )
    assert actor.kind == "human"
    assert actor.id == "lead"


def test_person_lookup(people_config):
    assert identity.person("priya")["sites"] == ["warehouse-2"]
    assert identity.person("nobody") is None


def test_display_prefers_username(people_config):
    assert identity.display("priya") == "@priya"
    assert identity.display("finance") == "Finance Approver"
    assert identity.display("guest:x") == "guest:x"


def test_display_strips_at_and_falls_back_to_id(tmp_path, monkeypatch):
    _tmp_config(
        tmp_path,
        monkeypatch,
        'people: [{id: a, name: "", username: "@ann", switch_ids: []},'
        ' {id: b, name: "", username: "", switch_ids: []}]\n',
    )
    try:
        assert identity.display("a") == "@ann"
        assert identity.display("b") == "b"
    finally:
        config.clear_caches()


def test_is_known(people_config):
    assert identity.is_known("@switch-user-lead:test") is True
    assert identity.is_known("@nobody:test") is False
    assert identity.is_known("") is False


def test_placeholders_clean_fixture(people_config):
    assert identity.placeholders() == []


def test_placeholders_flags_empty_lead_and_priya(tmp_path, monkeypatch):
    _tmp_config(
        tmp_path,
        monkeypatch,
        "people:\n"
        "  - {id: lead, name: Lead, role: lead, username: '', switch_ids: []}\n"
        "  - {id: priya, name: Priya, role: site_manager, username: '<priya>',"
        " switch_ids: ['<filled in>']}\n",
    )
    try:
        assert identity.placeholders() == [
            "lead: switch_ids is empty",
            "priya: switch_ids contains a placeholder: <filled in>",
            "priya: username contains a placeholder: <priya>",
        ]
    finally:
        config.clear_caches()


def test_missing_people_yaml_means_guests(tmp_path, monkeypatch):
    _tmp_config(tmp_path, monkeypatch)
    try:
        actor = identity.actor_for("@switch-user-lead:test", "lead")
        assert actor == Actor("human", "guest:@switch-user-lead:test", "lead", None)
        assert identity.placeholders() == ["people.yaml is missing"]
        assert identity.is_known("@switch-user-lead:test") is False
    finally:
        config.clear_caches()


def test_repo_people_yaml_parses_and_has_four_people(monkeypatch):
    monkeypatch.delenv("CARBON_ROOM_CONFIG_DIR", raising=False)
    config.clear_caches()
    try:
        people = config.load_people()["people"]
        assert [p["id"] for p in people] == ["lead", "priya", "finance", "auditor"]
        assert [p["role"] for p in people] == ["lead", "site_manager", "finance", "auditor"]
        assert all(isinstance(p["username"], str) and isinstance(p["switch_ids"], list) for p in people)
        assert people[1]["sites"] == ["warehouse-2"]
        assert not any("<" in p for p in identity.placeholders())
    finally:
        config.clear_caches()
