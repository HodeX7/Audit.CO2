"""Agent registration CLI: python -m carbon_room.room.register."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import httpx
from dotenv import set_key

from carbon_room.room.ports import AGENT_NAMES, AGENT_TITLES
from carbon_room.room.settings import env_name, read_env

CONNECTOR_TYPE: str = "carbon-room-python"
DESCRIPTIONS: dict[str, str] = {
    "carbon-room": "Runs the month-end emissions close: posts the plan, the summary and the publish.",
    "collector": "Collects the month's bills and invoices into the ledger.",
    "watchdog": "Checks every ledger row and opens a thread for each gap, with a named owner.",
    "reporter": "Drafts the report and traces any figure back to its source.",
}

_HINT_NO_SERVER = "SWITCH_SERVER is not set. Put the server address from Switch Console in .env."
_HINT_NO_REGKEY = (
    "SWITCH_REGISTRATION_KEY is not set. Create one on the Gateway's API Keys page, or create "
    "the agents in Switch Console and run register --from-console .switch/agents once"
)
_ADDRESSING_HINT = 'set "Anyone" in Switch Console → agent settings.'


def registration_body(name: str) -> dict:
    return {
        "name": name,
        "description": DESCRIPTIONS[name],
        "connector_type": CONNECTOR_TYPE,
        "display_name": AGENT_TITLES[name],
        "integration_profile": {
            "connection_model": "always_on",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": [],
        },
    }


class _Env:
    """The env file plus process environment, with writes going to the file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            path.touch()
        self.values = {k: v.strip() for k, v in read_env(path).items()}

    def get(self, name: str) -> str:
        return self.values.get(name, "")

    def set(self, name: str, value: str) -> None:
        set_key(str(self.path), name, value, quote_mode="never")
        self.values[name] = value


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict) and data.get("detail"):
            return str(data["detail"])
    except ValueError:
        pass
    return response.text[:200]


def _creds(env: _Env, name: str) -> tuple[str, str]:
    return env.get(env_name(name, "ID")), env.get(env_name(name, "KEY"))


def _import_console(env: _Env, directory: Path) -> None:
    for name in AGENT_NAMES:
        file = directory / f"{name}.json"
        try:
            values = json.loads(file.read_text())["env"]
            agent_id = values["SWITCH_AGENT_ID"]
            token = values["SWITCH_API_TOKEN"]
        except (OSError, ValueError, KeyError, TypeError):
            print(f"{name}: no {directory}/{name}.json; create the agent in Switch Console first.")
            continue
        env.set(env_name(name, "ID"), agent_id)
        env.set(env_name(name, "KEY"), token)
        endpoint = values.get("SWITCH_API_ENDPOINT")
        if endpoint and not env.get("SWITCH_SERVER"):
            env.set("SWITCH_SERVER", endpoint)
        print(f"{name}: imported from Switch Console")


def _register(env: _Env, client: httpx.Client, server: str) -> None:
    for name in AGENT_NAMES:
        agent_id, key = _creds(env, name)
        if agent_id and key:
            print(f"{name}: already registered, skipping")
            continue
        reg_key = env.get("SWITCH_REGISTRATION_KEY")
        if not reg_key:
            print(_HINT_NO_REGKEY)
            return
        try:
            response = client.post(
                f"{server}/agents",
                headers={"Authorization": f"Bearer {reg_key}"},
                json=registration_body(name),
            )
        except httpx.TransportError:
            print(f"{name}: registration failed: can't reach {server}")
            continue
        status = response.status_code
        if status in (200, 201):
            try:
                data = response.json()
                new_id, new_key = data["id"], data["api_key"]
            except (ValueError, KeyError, TypeError):
                print(f"{name}: registration failed ({status}): {_detail(response)}")
                continue
            env.set(env_name(name, "ID"), str(new_id))
            env.set(env_name(name, "KEY"), str(new_key))
            print(f"{name}: registered")
        elif status == 409:
            print(
                f"{name}: name already taken. If it is yours, copy its id and key into .env "
                "(docs/setup-switch.md); otherwise delete it in the Gateway."
            )
        else:
            print(f"{name}: registration failed ({status}): {_detail(response)}")


def _set_addressing(env: _Env, client: httpx.Client, server: str) -> None:
    for name in AGENT_NAMES:
        agent_id, key = _creds(env, name)
        if not (agent_id and key):
            continue
        try:
            response = client.post(
                f"{server}/agents/{agent_id}/ops/update_agent_detail",
                headers={"Authorization": f"Bearer {key}"},
                json={"agent_id": agent_id, "addressing": "anyone"},
            )
        except httpx.TransportError:
            print(f"{name}: couldn't set addressing (no response); {_ADDRESSING_HINT}")
            continue
        status = response.status_code
        if 200 <= status < 300:
            print(f"{name}: addressing set to anyone")
        elif status in (400, 403):
            print(f"{name}: Switch refused addressing=anyone; {_ADDRESSING_HINT}")
        else:
            print(f"{name}: couldn't set addressing ({status}); {_ADDRESSING_HINT}")


def _invite(env: _Env, client: httpx.Client, server: str, room_id: str) -> None:
    host_id, host_key = _creds(env, "carbon-room")
    if not (host_id and host_key):
        return
    hint = "invite it to the room in Switch Console."

    def fail_all() -> None:
        for name in AGENT_NAMES:
            print(f"{name}: {hint}")

    headers = {"Authorization": f"Bearer {host_key}"}
    try:
        response = client.get(f"{server}/agents/{host_id}/ops", headers=headers)
        response.raise_for_status()
        props = response.json()["operations"]["invite_agent_to_room"]["input_schema"].get(
            "properties", {}
        )
        room_key = next(p for p in props if "room" in p)
        agent_key = next(p for p in props if "agent" in p)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        fail_all()
        return
    for name in AGENT_NAMES:
        agent_id, _ = _creds(env, name)
        if not agent_id:
            continue
        value = agent_id if "id" in agent_key else name
        try:
            result = client.post(
                f"{server}/agents/{host_id}/ops/invite_agent_to_room",
                headers=headers,
                json={room_key: room_id, agent_key: value},
            )
            ok = 200 <= result.status_code < 300
        except httpx.TransportError:
            ok = False
        print(f"{name}: invited to the room" if ok else f"{name}: {hint}")


def main(
    argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None
) -> int:
    parser = argparse.ArgumentParser(prog="python -m carbon_room.room.register")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--from-console", dest="from_console", default=None)
    parser.add_argument("--room", default=None)
    args = parser.parse_args(argv)

    env = _Env(Path(args.env))
    if args.from_console:
        _import_console(env, Path(args.from_console))
    server = env.get("SWITCH_SERVER").rstrip("/")
    if not server:
        print(_HINT_NO_SERVER)
        return 1
    if args.room:
        env.set("SWITCH_ROOM_ID", args.room)

    with httpx.Client(transport=transport, timeout=15) as client:
        if not args.from_console:
            _register(env, client, server)
        _set_addressing(env, client, server)
        room_id = args.room or env.get("SWITCH_ROOM_ID")
        if room_id:
            _invite(env, client, server, room_id)

    return 0 if all(all(_creds(env, n)) for n in AGENT_NAMES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
