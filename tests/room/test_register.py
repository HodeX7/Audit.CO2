"""Tests for the agent registration CLI."""

from __future__ import annotations

import json
import logging
import os

import httpx
import pytest
from dotenv import dotenv_values

from carbon_room.room.ports import AGENT_NAMES
from carbon_room.room.register import DESCRIPTIONS, main, registration_body

REFUSED = 'Switch refused addressing=anyone; set "Anyone" in Switch Console → agent settings.'


class Recorder:
    """MockTransport handler that records calls.

    overrides maps (method, path) to a Response, an exception, or a callable(request, body).
    register_hook, when set, is called for POST /agents and may return a Response or None.
    """

    def __init__(self, register_hook=None, invite_props=None, ops_body=None):
        self.calls: list[dict] = []
        self.overrides: dict = {}
        self.register_hook = register_hook
        self.invite_props = invite_props or {"room_id": {}, "agent_id": {}}
        self.ops_body = ops_body
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "host": request.url.host,
                "json": body,
                "auth": request.headers.get("Authorization"),
                "conn": request.headers.get("X-Switch-Connection-Id"),
            }
        )
        path = request.url.path
        key = (request.method, path)
        if key in self.overrides:
            return self.overrides[key](request, body)
        if request.method == "POST" and path == "/agents":
            if self.register_hook is not None:
                out = self.register_hook(request, body)
                if isinstance(out, httpx.Response):
                    return out
            name = body["name"]
            return httpx.Response(201, json={"id": f"agent-{name}", "api_key": f"key-{name}-secret"})
        if path.endswith("/ops/update_agent_detail"):
            return httpx.Response(200, json={"result": {}})
        if request.method == "GET" and path.endswith("/ops"):
            if self.ops_body is not None:
                return httpx.Response(200, json=self.ops_body)
            return httpx.Response(
                200,
                json={
                    "operations": {
                        "invite_agent_to_room": {
                            "description": "",
                            "input_schema": {"properties": self.invite_props},
                        }
                    }
                },
            )
        if path.endswith("/ops/invite_agent_to_room"):
            return httpx.Response(200, json={"result": {}})
        return httpx.Response(404)

    def posts(self, suffix):
        return [c for c in self.calls if c["method"] == "POST" and c["path"].endswith(suffix)]

    def register_posts(self):
        return [c for c in self.calls if c["method"] == "POST" and c["path"] == "/agents"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("SWITCH_"):
            monkeypatch.delenv(k)


def make_env(tmp_path, server="http://sw.test/", regkey="reg-secret"):
    p = tmp_path / ".env"
    lines = []
    if server:
        lines.append(f"SWITCH_SERVER={server}")
    if regkey:
        lines.append(f"SWITCH_REGISTRATION_KEY={regkey}")
    p.write_text("\n".join(lines) + ("\n" if lines else ""))
    return p


def run(path, rec, *extra):
    return main(["--env", str(path), *extra], transport=rec.transport)


def test_registration_body():
    assert registration_body("watchdog") == {
        "name": "watchdog",
        "description": DESCRIPTIONS["watchdog"],
        "connector_type": "carbon-room-python",
        "display_name": "Watchdog",
        "integration_profile": {
            "connection_model": "always_on",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": [],
        },
    }


def test_first_run_registers_four_and_writes_env(tmp_path, capsys):
    path = make_env(tmp_path)
    rec = Recorder()
    assert run(path, rec) == 0
    posts = rec.register_posts()
    assert [c["json"]["name"] for c in posts] == list(AGENT_NAMES)
    assert all(c["auth"] == "Bearer reg-secret" for c in posts)
    values = dotenv_values(path)
    for name in AGENT_NAMES:
        up = name.upper().replace("-", "_")
        assert values[f"SWITCH_AGENT_{up}_ID"] == f"agent-{name}"
        assert values[f"SWITCH_AGENT_{up}_KEY"] == f"key-{name}-secret"
    assert "collector: registered" in capsys.readouterr().out


def test_addressing_calls_use_agent_keys(tmp_path):
    path = make_env(tmp_path)
    rec = Recorder()
    run(path, rec)
    calls = rec.posts("/ops/update_agent_detail")
    assert len(calls) == 4
    for name, c in zip(AGENT_NAMES, calls, strict=True):
        assert c["path"] == f"/agents/agent-{name}/ops/update_agent_detail"
        assert c["auth"] == f"Bearer key-{name}-secret"
        assert c["json"] == {"agent_id": f"agent-{name}", "addressing": "anyone"}
        assert c["conn"] is None


def test_second_run_skips_all(tmp_path, capsys):
    path = make_env(tmp_path)
    rec = Recorder()
    run(path, rec)
    capsys.readouterr()
    rec.calls.clear()
    assert run(path, rec) == 0
    assert rec.register_posts() == []
    assert capsys.readouterr().out.count("already registered, skipping") == 4
    assert len(rec.posts("/ops/update_agent_detail")) == 4


def test_409_message_and_continue(tmp_path, capsys):
    path = make_env(tmp_path)

    def conflict(request, body):
        if body["name"] == "collector":
            return httpx.Response(409, json={"detail": "taken"})
        return None

    rec = Recorder(register_hook=conflict)
    assert run(path, rec) == 1
    out = capsys.readouterr().out.splitlines()
    assert (
        "collector: name already taken. If it is yours, copy its id and key into .env "
        "(docs/setup-switch.md); otherwise delete it in the Gateway."
    ) in out
    values = dotenv_values(path)
    assert "SWITCH_AGENT_COLLECTOR_ID" not in values
    for name in ("carbon-room", "watchdog", "reporter"):
        assert values[f"SWITCH_AGENT_{name.upper().replace('-', '_')}_ID"] == f"agent-{name}"


def test_other_error_exit_code_1(tmp_path, capsys):
    path = make_env(tmp_path)

    def boom(request, body):
        if body["name"] == "reporter":
            return httpx.Response(500, json={"detail": "db down"})
        return None

    rec = Recorder(register_hook=boom)
    assert run(path, rec) == 1
    assert "reporter: registration failed (500): db down" in capsys.readouterr().out


def test_network_error(tmp_path, capsys):
    path = make_env(tmp_path)

    def down(request, body):
        raise httpx.ConnectError("nope")

    rec = Recorder(register_hook=down)
    assert run(path, rec) == 1
    assert (
        "carbon-room: registration failed: can't reach http://sw.test"
        in capsys.readouterr().out.splitlines()
    )


def test_missing_server(tmp_path, capsys):
    path = make_env(tmp_path, server="")
    rec = Recorder()
    assert run(path, rec) == 1
    assert rec.calls == []
    assert "SWITCH_SERVER is not set." in capsys.readouterr().out


def test_missing_registration_key(tmp_path, capsys):
    path = make_env(tmp_path, regkey="")
    rec = Recorder()
    assert run(path, rec) == 1
    assert rec.register_posts() == []
    assert capsys.readouterr().out.count("SWITCH_REGISTRATION_KEY is not set.") == 1


def console_dir(tmp_path, names=AGENT_NAMES):
    d = tmp_path / "agents"
    d.mkdir()
    for name in names:
        (d / f"{name}.json").write_text(
            json.dumps(
                {
                    "env": {
                        "SWITCH_API_ENDPOINT": "http://console.test",
                        "SWITCH_API_TOKEN": f"tok-{name}-secret",
                        "SWITCH_AGENT_ID": f"cid-{name}",
                    }
                }
            )
        )
    return d


def test_from_console_imports_files(tmp_path):
    path = make_env(tmp_path, server="", regkey="")
    d = console_dir(tmp_path)
    rec = Recorder()
    assert run(path, rec, "--from-console", str(d)) == 0
    values = dotenv_values(path)
    assert values["SWITCH_SERVER"] == "http://console.test"
    assert values["SWITCH_AGENT_WATCHDOG_ID"] == "cid-watchdog"
    assert values["SWITCH_AGENT_WATCHDOG_KEY"] == "tok-watchdog-secret"
    assert rec.register_posts() == []
    addressing = rec.posts("/ops/update_agent_detail")
    assert len(addressing) == 4
    assert all(c["host"] == "console.test" for c in addressing)


def test_from_console_missing_file(tmp_path, capsys):
    path = make_env(tmp_path, server="", regkey="")
    d = console_dir(tmp_path, names=AGENT_NAMES[:3])
    rec = Recorder()
    assert run(path, rec, "--from-console", str(d)) == 1
    assert (
        f"reporter: no {d}/reporter.json; create the agent in Switch Console first."
        in capsys.readouterr().out
    )


def test_addressing_refused_prints_console_hint(tmp_path, capsys):
    path = make_env(tmp_path)
    rec = Recorder()
    for name in AGENT_NAMES:
        rec.overrides[("POST", f"/agents/agent-{name}/ops/update_agent_detail")] = (
            lambda request, body: httpx.Response(403, json={"detail": "no"})
        )
    assert run(path, rec) == 0
    out = capsys.readouterr().out.splitlines()
    for name in AGENT_NAMES:
        assert f"{name}: {REFUSED}" in out


def test_invite_calls_with_schema_keys(tmp_path, capsys):
    path = make_env(tmp_path)
    rec = Recorder()
    assert run(path, rec, "--room", "room-9") == 0
    assert dotenv_values(path)["SWITCH_ROOM_ID"] == "room-9"
    gets = [c for c in rec.calls if c["method"] == "GET"]
    assert [c["path"] for c in gets] == ["/agents/agent-carbon-room/ops"]
    invites = rec.posts("/ops/invite_agent_to_room")
    assert len(invites) == 4
    for name, c in zip(AGENT_NAMES, invites, strict=True):
        assert c["path"] == "/agents/agent-carbon-room/ops/invite_agent_to_room"
        assert c["json"] == {"room_id": "room-9", "agent_id": f"agent-{name}"}
    assert "watchdog: invited to the room" in capsys.readouterr().out


def test_invite_failure_prints_hint(tmp_path, capsys):
    path = make_env(tmp_path)
    rec = Recorder(ops_body={"operations": {"post_message": {"input_schema": {}}}})
    assert run(path, rec, "--room", "room-9") == 0
    out = capsys.readouterr().out.splitlines()
    for name in AGENT_NAMES:
        assert f"{name}: invite it to the room in Switch Console." in out
    assert rec.posts("/ops/invite_agent_to_room") == []


def test_invite_by_name_when_schema_says_agent(tmp_path):
    path = make_env(tmp_path)
    rec = Recorder(invite_props={"room": {}, "agent": {}})
    run(path, rec, "--room", "r")
    invites = rec.posts("/ops/invite_agent_to_room")
    assert [c["json"] for c in invites] == [{"room": "r", "agent": n} for n in AGENT_NAMES]


def test_key_never_printed_or_logged(tmp_path, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    outputs = []

    path = make_env(tmp_path)
    run(path, Recorder(), "--room", "room-9")
    outputs.append(capsys.readouterr())

    sub = tmp_path / "two"
    sub.mkdir()
    path2 = make_env(sub)
    run(path2, Recorder(register_hook=lambda r, b: httpx.Response(409)))
    outputs.append(capsys.readouterr())

    sub3 = tmp_path / "three"
    sub3.mkdir()
    path3 = make_env(sub3, server="", regkey="")
    d = console_dir(sub3)
    run(path3, Recorder(), "--from-console", str(d))
    outputs.append(capsys.readouterr())

    text = caplog.text + "".join(o.out + o.err for o in outputs)
    for needle in ("reg-secret", "key-", "tok-", "Bearer"):
        assert needle not in text
