# SPEC-09 · Agent registration CLI
Stories: P3-1.2 · Branch: `p3-s09-register` · PR title: "P3-S09 (1.2): agent registration CLI"
Depends on (must be merged): SPEC-06 (`env_name`) · Wave: 1, started after SPEC-06 merges · Estimated session time: 1 h

## 1. Goal
`python -m carbon_room.room.register` registers the four agents with Switch and writes each id and key to `.env`
without printing them. It then sets each agent's addressing to "anyone" and tries to invite each agent to the
room. Running it twice is safe. A second mode imports agents created in Switch Console from
`.switch/agents/*.json`.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.5 (Auth and registration, Addressing), §2 and §3.10
- `carbon_room/room/settings.py` (`env_name`, `read_env`) and `carbon_room/room/ports.py` (`AGENT_NAMES`,
  `AGENT_TITLES`)
- python-dotenv `dotenv_values` and `set_key(path, key, value, quote_mode="never")`

## 3. Files
- Create `carbon_room/room/register.py`
- Create `tests/room/test_register.py`
- Modify `docs/switch-protocol-notes.md`: replace only the body of `## S09 register`

## 4. Public interface
```python
CONNECTOR_TYPE: str = "carbon-room-python"
DESCRIPTIONS: dict[str, str] = {
    "carbon-room": "Runs the month-end emissions close: posts the plan, the summary and the publish.",
    "collector": "Collects the month's bills and invoices into the ledger.",
    "watchdog": "Checks every ledger row and opens a thread for each gap, with a named owner.",
    "reporter": "Drafts the report and traces any figure back to its source.",
}
def registration_body(name: str) -> dict
def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int
```
`if __name__ == "__main__": raise SystemExit(main())`. It uses a synchronous `httpx.Client(transport=transport,
timeout=15)`, not `OpsClient`.

## 5. Behaviour
1. **Arguments.** `--env PATH` (default `.env`), `--from-console DIR` and `--room ROOM_ID`.
2. **Env file.**
   - It is created empty when missing.
   - Values come from `dotenv_values(PATH)`, and a variable set in the process environment overrides the file.
   - Every write uses `set_key(PATH, name, value, quote_mode="never")`.
3. **`registration_body(name)`** returns `{"name": name, "description": DESCRIPTIONS[name], "connector_type":
   "carbon-room-python", "display_name": AGENT_TITLES[name], "integration_profile": {"connection_model":
   "always_on", "message_exchange": True, "pre_invocation_mediation": [], "post_invocation_mediation": [],
   "event_reporting": []}}`.
4. **Server.**
   - `SWITCH_SERVER` is stripped of trailing `/`.
   - If it is missing in mode A, print `SWITCH_SERVER is not set. Put the server address from Switch Console in
     .env.` and return 1. Make no request.
   - In mode B, fill it from the console files first (rule 6).
5. **Mode A (default),** for each agent in `AGENT_NAMES` order:
   1. **Already registered.** If both `env_name(name, "ID")` and `env_name(name, "KEY")` have values, print
      `<name>: already registered, skipping` and go to the next agent.
   2. **Registration key.** If one is needed and `SWITCH_REGISTRATION_KEY` is empty, print
      `SWITCH_REGISTRATION_KEY is not set. Create one on the Gateway's API Keys page, or create the agents in
      Switch Console and run register --from-console .switch/agents` once, and stop registering. Already-present
      agents still get addressing and invite.
   3. **Register.** Send `POST {server}/agents` with `Authorization: Bearer <registration key>` and
      `json=registration_body(name)`.
   4. **200 or 201** with a JSON body holding `id` and `api_key`: write both variables, then print
      `<name>: registered`.
   5. **409:** print `<name>: name already taken. If it is yours, copy its id and key into .env
      (docs/setup-switch.md); otherwise delete it in the Gateway.`
   6. **Any other status:** print `<name>: registration failed (<status>): <detail>`. `detail` is the JSON
      `detail` when present, else the body text cut to 200 characters.
   7. **`httpx.TransportError`:** print `<name>: registration failed: can't reach <server>`.
6. **Mode B (`--from-console DIR`),** for each agent:
   - Read `DIR/<name>.json` and its `env` object. Write `SWITCH_AGENT_<NAME>_ID` from `SWITCH_AGENT_ID`, and
     `SWITCH_AGENT_<NAME>_KEY` from `SWITCH_API_TOKEN`. This always overwrites.
   - When `SWITCH_SERVER` is unset, write it from `SWITCH_API_ENDPOINT`.
   - Print `<name>: imported from Switch Console`.
   - A missing or unreadable file prints `<name>: no <DIR>/<name>.json; create the agent in Switch Console
     first.`
   - Mode B never calls `POST /agents`.
7. **Room id.** When `--room` is given, write `SWITCH_ROOM_ID` with it.
8. **Addressing,** for every agent that now has an id and key, after the registration loop:
   - Send `POST {server}/agents/{id}/ops/update_agent_detail` with `Bearer <agent key>`,
     `X-Switch-Connection-Id` absent, and `json={"agent_id": id, "addressing": "anyone"}`.
   - **2xx:** print `<name>: addressing set to anyone`.
   - **400 or 403:** print `<name>: Switch refused addressing=anyone; set "Anyone" in Switch Console → agent
     settings.`
   - **Any other status or a network error:** print `<name>: couldn't set addressing (<status or "no
     response">); set "Anyone" in Switch Console → agent settings.`
   - This never changes the exit code.
9. **Invite.** This runs when the room id comes from `--room` or `SWITCH_ROOM_ID` and carbon-room has an id and
   key. Otherwise it is skipped silently.
   1. Send `GET {server}/agents/{carbon-room id}/ops` with carbon-room's key. Take
      `operations["invite_agent_to_room"]["input_schema"].get("properties", {})`.
   2. `room_key` is the first property name containing `room`. `agent_key` is the first containing `agent`.
   3. If the op or either key is missing, or the GET fails, print `<name>: invite it to the room in Switch
      Console.` for every agent and stop.
   4. Otherwise, for each agent with an id, send `POST {server}/agents/{carbon-room id}/ops/invite_agent_to_room`
      with `{room_key: room_id, agent_key: value}`. `value` is the agent's Switch id when `agent_key` contains
      `id`, else its name.
   5. **2xx:** print `<name>: invited to the room`. **Anything else:** print `<name>: invite it to the room in
      Switch Console.`
   6. This never changes the exit code.
10. **Exit code.** Return 0 when all four agents have an id and a key at the end, else 1.
11. **Secrets.** No printed line or log line contains a registration key, an agent key or an `Authorization`
    header. `print` is allowed here, since this is a CLI entry point.
12. **Idempotence.** A second run with a complete `.env` makes zero `POST /agents` calls, and the same
    addressing and invite calls as the first run.

## 6. Test plan
Each test uses a tmp `.env` and `monkeypatch.delenv` for every `SWITCH_*` variable. `httpx.MockTransport(handler)`
records `(method, path, json body, Authorization header)`. By default it answers:
- `POST /agents` with 201 `{"id": f"agent-{name}", "api_key": f"key-{name}-secret"}`, where `name` is from the
  body
- `update_agent_detail` with 200 `{"result": {}}`
- `GET …/ops` with 200 `{"operations": {"invite_agent_to_room": {"description": "", "input_schema":
  {"properties": {"room_id": {}, "agent_id": {}}}}}}`
- `invite_agent_to_room` with 200 `{"result": {}}`

The `.env` starts with `SWITCH_SERVER=http://sw.test/` and `SWITCH_REGISTRATION_KEY=reg-secret`. Call
`main(["--env", str(path)], transport=mock)`.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_registration_body` | — | `registration_body("watchdog")` | equals the rule-3 dict with `display_name == "Watchdog"` and `description == DESCRIPTIONS["watchdog"]` [3] |
| `test_first_run_registers_four_and_writes_env` | defaults | `main(...)` | returns 0; 4 `POST /agents` calls in `AGENT_NAMES` order, each with `Bearer reg-secret`; `dotenv_values(path)` has `SWITCH_AGENT_COLLECTOR_ID == "agent-collector"` and `SWITCH_AGENT_COLLECTOR_KEY == "key-collector-secret"` (all four agents); stdout has `"collector: registered"` [5] |
| `test_addressing_calls_use_agent_keys` | defaults | `main(...)` | 4 POSTs to `/agents/agent-<name>/ops/update_agent_detail`, each with `Bearer key-<name>-secret` and body `{"agent_id": "agent-<name>", "addressing": "anyone"}` [8] |
| `test_second_run_skips_all` | run `main` once; clear the recorded calls | `main(...)` again | 0 `POST /agents`; stdout has 4 `already registered, skipping` lines; 4 addressing calls again; returns 0 [5, 12] |
| `test_409_message_and_continue` | `POST /agents` for `collector` returns 409 | `main(...)` | the stdout line is exactly `collector: name already taken. If it is yours, copy its id and key into .env (docs/setup-switch.md); otherwise delete it in the Gateway.`; the other 3 are registered; returns 1 [5, 10] |
| `test_other_error_exit_code_1` | `POST /agents` for `reporter` returns 500 `{"detail": "db down"}` | `main(...)` | stdout has `reporter: registration failed (500): db down`; returns 1 [5, 10] |
| `test_network_error` | the handler raises `httpx.ConnectError` for `POST /agents` | `main(...)` | stdout has `carbon-room: registration failed: can't reach http://sw.test`; returns 1 [5] |
| `test_missing_server` | `.env` without `SWITCH_SERVER` | `main(...)` | returns 1; no requests; stdout has `SWITCH_SERVER is not set.` [4] |
| `test_missing_registration_key` | `.env` without `SWITCH_REGISTRATION_KEY` | `main(...)` | returns 1; no `POST /agents`; the hint is printed exactly once [5] |
| `test_from_console_imports_files` | `.env` has no `SWITCH_SERVER`; tmp dir with 4 `<name>.json` files `{"env": {"SWITCH_API_ENDPOINT": "http://console.test", "SWITCH_API_TOKEN": "tok-<name>-secret", "SWITCH_AGENT_ID": "cid-<name>"}}` | `main(["--env", p, "--from-console", d], …)` | `.env` has `SWITCH_SERVER == "http://console.test"`, `SWITCH_AGENT_WATCHDOG_ID == "cid-watchdog"` and `SWITCH_AGENT_WATCHDOG_KEY == "tok-watchdog-secret"`; 0 `POST /agents`; addressing calls go to `http://console.test`; returns 0 [6] |
| `test_from_console_missing_file` | only 3 files | mode B | stdout has `reporter: no <d>/reporter.json; create the agent in Switch Console first.`; returns 1 [6, 10] |
| `test_addressing_refused_prints_console_hint` | `update_agent_detail` returns 403 for every agent | `main(...)` | 4 lines `<name>: Switch refused addressing=anyone; set "Anyone" in Switch Console → agent settings.`; returns 0 [8] |
| `test_invite_calls_with_schema_keys` | `--room room-9` | `main(...)` | `.env` has `SWITCH_ROOM_ID == "room-9"`; 1 `GET /agents/agent-carbon-room/ops`; 4 POSTs to `/agents/agent-carbon-room/ops/invite_agent_to_room` with bodies `{"room_id": "room-9", "agent_id": "agent-<name>"}`; stdout has `watchdog: invited to the room` [7, 9] |
| `test_invite_failure_prints_hint` | `--room room-9`; the `GET …/ops` result lacks `invite_agent_to_room` | `main(...)` | 4 lines `<name>: invite it to the room in Switch Console.`; returns 0 [9] |
| `test_invite_by_name_when_schema_says_agent` | properties `{"room": {}, "agent": {}}` | `--room r` | bodies `{"room": "r", "agent": "<name>"}` [9] |
| `test_key_never_printed_or_logged` | `caplog.set_level(logging.DEBUG)`; one full run, one 409 run, one mode-B run | `capsys.readouterr()` | none of `reg-secret`, `key-`, `tok-` or `Bearer` appears in stdout, stderr or `caplog.text` [11] |

## 7. Fixtures and doubles
- `httpx.MockTransport` only.
- `docs/switch-protocol-notes.md`, the body of `## S09 register`, at most 20 lines:
  - the registration request and response
  - 409 handling
  - the console JSON shape
  - the addressing call
  - the invite heuristic
  - that real behaviour is confirmed in M2

## 8. Manual check
After M1, run `make register` (or the module directly), and then run it again:
- The first run registers four agents (or prints the 409 hint).
- The second run prints four `already registered, skipping` lines.
- In Mattermost, all four agents are participants in `october-close`. If the invite printed hints, invite them in
  Switch Console.

## 9. Done when
- [ ] Running it twice is safe
- [ ] Manual check: all four agents appear as participants in `october-close` (by invite, or by hand per the hint)
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
Connecting (SPEC-07) and the Makefile target (SPEC-16).

## 11. Open questions
None block execution. The invite heuristic and the addressing body follow the docs and will be confirmed in M2.
The invite step is third in the cut order: if it misbehaves, invite by hand.
