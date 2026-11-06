import re
from pathlib import Path

import pytest

from carbon_room.room.ports import AGENT_NAMES
from carbon_room.room.settings import AgentCreds, env_name, load_settings, missing, read_env

ENV = {"SWITCH_SERVER": "http://127.0.0.1:7777/", "SWITCH_ROOM_ID": "room-1"}
for _a in AGENT_NAMES:
    _n = _a.upper().replace("-", "_")
    ENV[f"SWITCH_AGENT_{_n}_ID"] = f"agent-{_a}"
    ENV[f"SWITCH_AGENT_{_n}_KEY"] = f"key-{_a}-secret"

ROOT = Path(__file__).resolve().parents[2]


def test_env_name():
    assert env_name("carbon-room", "ID") == "SWITCH_AGENT_CARBON_ROOM_ID"
    assert env_name("reporter", "KEY") == "SWITCH_AGENT_REPORTER_KEY"


def test_load_settings_reads_all_fields():
    env = {
        **ENV,
        "CARBON_ROOM_THREADS": "0",
        "CARBON_ROOM_ATTACHMENTS": "download",
        "MATTERMOST_PERMALINK_BASE": "http://mm.local/team/pl/",
        "SWITCH_MEDIA_PATH": "/agents/{agent_id}/media/{mxc}",
    }
    s = load_settings(env)
    assert s.server == "http://127.0.0.1:7777"
    assert s.room_id == "room-1"
    assert s.agents["watchdog"] == AgentCreds("watchdog", "agent-watchdog", "key-watchdog-secret")
    assert len(s.agents) == 4
    assert s.threads is False
    assert s.attachments_mode == "download"
    assert s.single_agent is False
    assert s.permalink_base == "http://mm.local/team/pl"
    assert s.media_path == "/agents/{agent_id}/media/{mxc}"
    assert s.inbox_dir == Path("data/inbox")


def test_defaults():
    s = load_settings(ENV)
    assert s.threads is True
    assert s.attachments_mode == "inbox"
    assert s.single_agent is False
    assert s.permalink_base is None
    assert s.media_path is None


def test_load_settings_missing_lists_every_name():
    with pytest.raises(ValueError) as ei:
        load_settings({})
    assert str(ei.value) == (
        "missing settings: SWITCH_SERVER, SWITCH_ROOM_ID, SWITCH_AGENT_CARBON_ROOM_ID, "
        "SWITCH_AGENT_CARBON_ROOM_KEY, SWITCH_AGENT_COLLECTOR_ID, SWITCH_AGENT_COLLECTOR_KEY, "
        "SWITCH_AGENT_WATCHDOG_ID, SWITCH_AGENT_WATCHDOG_KEY, SWITCH_AGENT_REPORTER_ID, "
        "SWITCH_AGENT_REPORTER_KEY"
    )


def test_whitespace_counts_as_missing():
    assert missing({**ENV, "SWITCH_ROOM_ID": "  "}) == ["SWITCH_ROOM_ID"]


def test_single_agent_needs_only_carbon_room():
    env = {
        "SWITCH_SERVER": "http://x",
        "SWITCH_ROOM_ID": "room-1",
        env_name("carbon-room", "ID"): "agent-carbon-room",
        env_name("carbon-room", "KEY"): "key-carbon-room-secret",
        "CARBON_ROOM_SINGLE_AGENT": "yes",
    }
    assert missing(env) == []
    s = load_settings(env)
    assert s.single_agent is True
    assert list(s.agents) == ["carbon-room"]


def test_missing_for_registration():
    assert missing({"SWITCH_SERVER": "http://x"}, for_run=False) == ["SWITCH_REGISTRATION_KEY"]


@pytest.mark.parametrize(
    "value,expected",
    [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("false", False),
     ("No", False), ("off", False), ("", True)],
)
def test_bool_flags_parse(value, expected):
    assert load_settings({**ENV, "CARBON_ROOM_THREADS": value}).threads is expected


def test_bad_flag_and_mode_raise():
    with pytest.raises(ValueError) as ei:
        load_settings({**ENV, "CARBON_ROOM_THREADS": "maybe"})
    assert str(ei.value) == "CARBON_ROOM_THREADS must be 1 or 0, got 'maybe'"
    with pytest.raises(ValueError) as ei:
        load_settings({**ENV, "CARBON_ROOM_ATTACHMENTS": "ftp"})
    assert str(ei.value) == "CARBON_ROOM_ATTACHMENTS must be download or inbox, got 'ftp'"


def test_read_env_file_and_environment(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("SWITCH_ROOM_ID=from-file\nSWITCH_SERVER=http://file\n")
    monkeypatch.setenv("SWITCH_SERVER", "http://env")
    got = read_env(p)
    assert got["SWITCH_ROOM_ID"] == "from-file"
    assert got["SWITCH_SERVER"] == "http://env"


def test_keys_not_in_repr_or_errors():
    assert "secret" not in repr(load_settings(ENV))
    with pytest.raises(ValueError) as ei:
        load_settings({**ENV, "SWITCH_SERVER": ""})
    assert "secret" not in str(ei.value)


def test_env_example_lists_every_variable():
    lines = (ROOT / ".env.example").read_text().splitlines()
    pairs = {}
    for line in lines:
        m = re.match(r"^([A-Z_]+)=(.*)$", line)
        if m:
            pairs[m.group(1)] = m.group(2)
    required = {"SWITCH_SERVER", "SWITCH_ROOM_ID", "SWITCH_REGISTRATION_KEY", "CARBON_ROOM_THREADS",
                "CARBON_ROOM_ATTACHMENTS", "CARBON_ROOM_SINGLE_AGENT", "MATTERMOST_PERMALINK_BASE",
                "SWITCH_MEDIA_PATH", "ANTHROPIC_API_KEY", "CARBON_ROOM_MODEL"}
    required |= {env_name(a, f) for a in AGENT_NAMES for f in ("ID", "KEY")}
    assert required <= set(pairs)
    for name, value in pairs.items():
        if name.endswith("_KEY"):
            assert value == "", name
