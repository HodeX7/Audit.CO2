"""SPEC-16: make doctor."""

from __future__ import annotations

import hashlib
import sys
from types import SimpleNamespace

import httpx
import pytest

from carbon_room import config
from carbon_room.room import doctor, settings
from carbon_room.room.doctor import CHECK_NAMES, Check, format_checks, run_checks
from carbon_room.room.ports import AGENT_NAMES

OK = SimpleNamespace(returncode=0, stdout="", stderr="")


class Runner:
    def __init__(self, *, docker=OK, init=OK):
        self.docker, self.init, self.calls = docker, init, []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        res = self.docker if argv[0] == "docker" else self.init
        if isinstance(res, Exception):
            raise res
        return res


def ok_transport(status=200, content_type="application/json", text='{"status": "ok"}'):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"content-type": content_type}, text=text)

    transport = httpx.MockTransport(handler)
    transport.requests = requests
    return transport


@pytest.fixture
def base(people_config, tmp_path):
    env = {"SWITCH_SERVER": "http://sw.test", "SWITCH_ROOM_ID": "room-1",
           "CARBON_ROOM_CONFIG_DIR": str(people_config)}
    for a in AGENT_NAMES:
        env[settings.env_name(a, "ID")] = "id"
        env[settings.env_name(a, "KEY")] = "key"
    seed = tmp_path / "data" / "seed" / "2026-10"
    seed.mkdir(parents=True)
    (seed / "a.pdf").write_bytes(b"A")
    (seed / "b.json").write_text("{}")
    return SimpleNamespace(env=env, root=tmp_path, cfg=people_config)


def go(base, env=None, runner=None, transport=None):
    return run_checks(env=base.env if env is None else env, runner=runner or Runner(),
                      transport=transport or ok_transport(), repo_root=base.root)


def set_mode(base, mode):
    (base.cfg / "carbon_room.yaml").write_text(f"llm: {{mode: {mode}}}\n")


def test_all_green(base):
    checks = go(base)
    assert len(checks) == 9
    assert all(c.ok for c in checks), checks
    assert [c.name for c in checks] == list(CHECK_NAMES)
    assert format_checks(checks).endswith("All 9 checks passed.")


def test_docker_not_running(base):
    c = go(base, runner=Runner(docker=SimpleNamespace(returncode=1, stdout="", stderr="")))[0]
    assert not c.ok
    assert c.detail == "docker info failed"
    assert c.fix == "Start Docker Desktop (the bundled Mattermost needs it)."


def test_docker_missing(base):
    c = go(base, runner=Runner(docker=FileNotFoundError()))[0]
    assert not c.ok and c.detail == "docker is not installed"


def test_switch_unset(base):
    base.env["SWITCH_SERVER"] = ""
    t = ok_transport()
    c = go(base, transport=t)[1]
    assert not c.ok
    assert c.detail == "SWITCH_SERVER is not set"
    assert c.fix == "Put the server address from Switch Console in .env as SWITCH_SERVER."
    assert t.requests == []


def test_switch_401(base):
    c = go(base, transport=ok_transport(401))[1]
    assert not c.ok
    assert c.detail == "401 from /health"
    assert c.fix == "Right host, wrong path: use the server address, not the Gateway."


def test_switch_gateway_html(base):
    c = go(base, transport=ok_transport(200, "text/html", "<html>hi</html>"))[1]
    assert not c.ok
    assert c.detail == "that address served a web page"
    assert c.fix.startswith("That's the Gateway.")


def test_switch_unreachable(base):
    def boom(request):
        raise httpx.ConnectError("nope")

    c = go(base, transport=httpx.MockTransport(boom))[1]
    assert not c.ok
    assert c.detail == "can't reach http://sw.test"
    assert c.fix.startswith("Start the server in Switch Console")


def test_switch_other_status(base):
    c = go(base, transport=ok_transport(503))[1]
    assert not c.ok
    assert c.detail == "/health returned 503"
    assert c.fix == "Check the server address in Switch Console."


def test_agent_keys_missing(base):
    del base.env["SWITCH_AGENT_WATCHDOG_KEY"]
    del base.env["SWITCH_AGENT_REPORTER_ID"]
    c = go(base)[2]
    assert not c.ok
    assert c.detail == "missing: SWITCH_AGENT_WATCHDOG_KEY, SWITCH_AGENT_REPORTER_ID"
    assert c.fix == "Run make register."


def test_room_id_missing(base):
    base.env["SWITCH_ROOM_ID"] = " "
    c = go(base)[3]
    assert not c.ok
    assert c.fix == ("Create the october-close room and put its id in .env as SWITCH_ROOM_ID "
                     "(docs/setup-switch.md).")


def test_people_placeholders(base):
    path = base.cfg / "people.yaml"
    path.write_text(path.read_text().replace('["@switch-user-lead:test"]', "[]"))
    config.clear_caches()
    c = go(base)[4]
    assert not c.ok
    assert c.detail == "lead: switch_ids is empty"
    assert c.fix == ("Fill in switch_ids and username for lead and priya in config/people.yaml "
                     "(docs/setup-switch.md).")


def test_carbon_room_yaml_missing(base):
    (base.cfg / "carbon_room.yaml").unlink()
    checks = go(base)
    assert not checks[5].ok
    assert checks[5].fix == "Pull main; P2 owns config/carbon_room.yaml."
    assert checks[7].ok and checks[7].detail == "skipped: no carbon_room.yaml"
    assert checks[8].ok and checks[8].detail == "not needed (mode=unknown)"


def test_db_init_fails(base):
    bad = SimpleNamespace(returncode=1, stdout="", stderr="boom\nsqlite3.OperationalError: locked\n")
    runner = Runner(init=bad)
    c = go(base, runner=runner)[6]
    assert not c.ok
    assert c.detail == "sqlite3.OperationalError: locked"
    assert c.fix == "Run .venv/bin/python -m carbon_room init and read the error."
    argv, kw = next(call for call in runner.calls if call[0][0] != "docker")
    assert argv == [sys.executable, "-m", "carbon_room", "init"]
    assert kw["cwd"] == base.root


def test_replay_cache_missing(base):
    set_mode(base, "replay")
    c = go(base)[7]
    assert not c.ok
    assert c.detail == "1 seed file(s) have no cached extraction: a.pdf"
    assert c.fix == ("Run make refresh-cache with an API key, or set llm.mode to rules in "
                     "config/carbon_room.yaml (ask P2).")


def test_replay_cache_present(base):
    set_mode(base, "replay")
    cache = base.root / "data" / "cache" / "extractions"
    cache.mkdir(parents=True)
    (cache / (hashlib.sha256(b"A").hexdigest() + ".json")).write_text("{}")
    assert go(base)[7].ok


def test_live_mode_needs_api_key(base):
    set_mode(base, "live")
    c = go(base)[8]
    assert not c.ok
    assert c.fix == "Put ANTHROPIC_API_KEY in .env, or use llm.mode rules or replay."
    base.env["ANTHROPIC_API_KEY"] = "x"
    assert go(base)[8].ok


def test_format_checks_failure_layout():
    checks = [Check("A", True, "", ""), Check("B", False, "d", "f")]
    assert format_checks(checks) == "✓ A\n✗ B — d\n    fix: f\n1 of 9 checks failed."


def test_doctor_never_prints_keys(base, monkeypatch, capsys):
    env = {k: "key-secret" for k in base.env}
    env["CARBON_ROOM_CONFIG_DIR"] = str(base.cfg)
    monkeypatch.setattr(settings, "read_env", lambda *a, **k: env)
    monkeypatch.chdir(base.root)
    doctor.main()
    assert "key-secret" not in capsys.readouterr().out
