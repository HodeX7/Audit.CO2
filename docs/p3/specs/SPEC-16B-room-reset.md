# SPEC-16B · Room reset (archive and recreate)
Stories: P3-6.3 (room part) · Branch: `p3-s16b-room-reset` · PR title: "P3-S16B (6.3): room reset"
Depends on (must be merged): SPEC-08 and SPEC-16 · Wave: 2–3 · Estimated session time: 0.75 h

> **Ready.** §0 comes from the schemas in `docs/switch-ops.json`. `create_room` takes `agent_names` at creation,
> so no separate invite step is needed. The only thing to check live is whether an agent key may archive and
> create rooms (§11).

## 0. Switch inputs (from `docs/switch-ops.json`)

| Constant (in `reset.py`) | Value | Source |
|---|---|---|
| `ARCHIVE_ROOM_ARG` | `"room_id"` | `archive_room` schema (required). It is reversible (`unarchive_room`). |
| `CREATE_ROOM_ARGS` | `name`, `description` and `agent_names` are required; `user_names` is optional | `create_room` schema. The default bridge is the bundled Mattermost. "The calling agent is not added automatically", so carbon-room is listed too. |
| `ROOM_DESCRIPTION` | `"Carbon Room demo: close a month of emissions in chat."` | free text |
| `CREATE_ROOM_ID_KEY` | `"id"` | create returns `{"id", "name", "matrix_room_id", "failed_attachments"}` |

## 1. Goal
`make reset-demo` also gives the demo a clean room. It archives the current room (the team's is
`emissions-reporting`), then creates a fresh one with the same name, with the four agents and the demo people
already in it, and writes the new room id to `.env`. Two rehearsals
then start identically. On any failure it prints the manual steps and exits 1. The local reset has already
happened by then.

## 2. Read before starting
- `docs/p3/specs/SPEC-16-makefile-doctor-reset.md` (the reset part) and `carbon_room/room/reset.py`
- `carbon_room/room/ops.py` (`OpsClient.call`, `SwitchError`), `carbon_room/room/settings.py` and
  `carbon_room/room/identity.py`
- `docs/switch-ops.json`: the `archive_room` and `create_room` entries

## 3. Files
- Modify `carbon_room/room/reset.py`: add `reset_room`, `demo_usernames` and the §0 constants, and replace the
  `ROOM_STEPS` branch of `main`
- Modify `tests/room/test_reset.py`: **delete** `test_reset_prints_room_steps_without_local_only` in the red
  commit, since the behaviour it pins is replaced
- Create `tests/room/test_reset_room.py`

## 4. Public interface
```python
ROOM_NAME: str = "october-close"
ROOM_DESCRIPTION: str = "Carbon Room demo: close a month of emissions in chat."
ARCHIVE_ROOM_ARG: str = "room_id"
CREATE_ROOM_ID_KEY: str = "id"
def demo_usernames() -> list[str]                       # non-empty people.yaml usernames, file order
async def reset_room(client: Any, *, room_id: str, room_name: str = ROOM_NAME,
                     user_names: list[str] | None = None) -> tuple[str, str]   # (new room id, its name)
def main(argv: Sequence[str] | None = None, *, input_fn=input, runner=subprocess.run,
         repo_root: Path = Path("."), env_path: Path = Path(".env"),
         client_factory: Callable[[Settings], Any] | None = None) -> int
```
`client_factory` defaults to `lambda s: OpsClient(s.server, s.agents["carbon-room"].agent_id,
s.agents["carbon-room"].api_key)`, with no connection id: room management ops aren't room-scoped.

## 5. Behaviour
1. **`demo_usernames()`** returns `[p["username"].lstrip("@") for p in config.load_people()["people"] if
   str(p.get("username") or "").strip()]`, or `[]` if `people.yaml` is missing.
2. **`reset_room(client, *, room_id, room_name, user_names)`**, in order:
   1. `archived = await client.call("archive_room", {"room_id": room_id})`. The new room reuses the old room's
      name: `name = archived.get("name") or room_name` when `archived` is a dict, else `room_name`. The team's
      room is `emissions-reporting`, so a hard-coded `october-close` would rename it.
   2. `args = {"name": name, "description": ROOM_DESCRIPTION, "agent_names": list(AGENT_NAMES)}`, plus
      `"user_names": user_names` when it is non-empty
   3. `result = await client.call("create_room", args)`, then `new_id = str(result["id"])`
   4. When `result.get("failed_attachments")` is non-empty, log a WARNING
   5. Return `(new_id, name)`
3. **`main` without `--local-only`**, after the local reset and init succeed (SPEC-16 rules 6–8):
   1. `settings = load_settings(read_env(env_path))`. A `ValueError` prints `Room reset skipped: <message>.`, then
      `ROOM_STEPS`, and returns 1.
   2. `client = client_factory(settings)`.
   3. `new_id, name = asyncio.run(...)` of a coroutine that awaits `reset_room(client, room_id=settings.room_id,
      user_names=demo_usernames())` and closes the client with `aclose` in a `finally`.
   4. `set_key(env_path, "SWITCH_ROOM_ID", new_id, quote_mode="never")`.
   5. Print `New room <name>: <new_id> (saved to .env). Restart make run so the agents join it.`
   6. Return 0.
4. **Failures.** A `SwitchError` or `KeyError` raised inside `reset_room` prints `Room reset failed at <op>:
   <error>.`, then `ROOM_STEPS`, and returns 1. `<op>` is the op being called. `.env` is not changed.
5. **Unchanged.** `--local-only` and cancellation behave exactly as in SPEC-16.

## 6. Test plan
Use a fake client class defined in the test. It records `(op, args)` for each `call`. It returns
`{"id": "room-old", "name": "emissions-reporting"}` for `archive_room`, and `{"id": "room-new", "name": <the
requested name>, "matrix_room_id": "!m", "failed_attachments": []}` for `create_room`. It can raise a `SwitchError`
for a chosen op, and it records `aclose`.

| Test | Act | Assert |
|---|---|---|
| `test_reset_room_call_sequence` | `reset_room(fake, room_id="room-old", user_names=["lead", "priya"])` | returns `("room-new", "emissions-reporting")`; the calls are exactly `[("archive_room", {"room_id": "room-old"}), ("create_room", {"name": "emissions-reporting", "description": "Carbon Room demo: close a month of emissions in chat.", "agent_names": ["carbon-room", "collector", "watchdog", "reporter"], "user_names": ["lead", "priya"]})]` [2] |
| `test_reset_room_name_fallback` | the fake's `archive_room` returns `{}` | `reset_room(fake, room_id="r")` | the `create_room` args have `name == "october-close"`; it returns `("room-new", "october-close")` [2] |
| `test_reset_room_without_users_omits_key` | `user_names=[]` | `reset_room(...)` | the `create_room` args have no `user_names` key [2] |
| `test_failed_attachments_warns` | `create_room` returns `failed_attachments: [{"kind": "x", "id": "y", "error": "z"}]`; caplog | `reset_room(...)` | still returns the id; a WARNING [2] |
| `test_demo_usernames` | `people_config` (fixture usernames `lead`, `priya`, `""`, `""`) | `demo_usernames()` | `["lead", "priya"]` [1] |
| `test_main_resets_room_and_writes_env` | the SPEC-16 reset layout; a tmp `.env` with full settings and `SWITCH_ROOM_ID=room-old`; `client_factory=lambda s: fake`; `people_config` | `main(["--yes"], …, env_path=env)` | returns 0; `dotenv_values(env)["SWITCH_ROOM_ID"] == "room-new"`; stdout has `"New room emissions-reporting: room-new (saved to .env). Restart make run so the agents join it."`; the fake was closed [3] |
| `test_main_room_failure_prints_steps` | the fake raises `SwitchError(403, "create_room", "denied")` on `create_room` | `main(["--yes"], …)` | returns 1; stdout has `"Room reset failed at create_room: create_room failed (403): denied."` and `ROOM_STEPS`; `.env` still says `room-old` [4] |
| `test_main_missing_settings` | `.env` without agent keys | `main(["--yes"], …)` | returns 1; the stdout room part starts with `"Room reset skipped: missing settings:"` [3] |
| `test_local_only_skips_room` | `client_factory` fails the test if called | `main(["--yes", "--local-only"], …)` | returns 0 [5] |
| `test_reset_constants_match_switch_ops_json` | load `docs/switch-ops.json` | — | `"room_id"` is in `archive_room`'s properties; `name`, `description` and `agent_names` are in `create_room`'s `required`; `user_names` is in its properties [§0] |

## 7. Fixtures and doubles
An in-test fake client, and `people_config` (SPEC-01).

## 8. Manual check
Run `make reset-demo` and type `reset`. In Mattermost the old room is archived. A new `october-close` holds the
four agents plus lead and priya. `.env` has its id, and `make run` connects to it.

## 9. Done when
- [ ] Two full rehearsals back to back start from an identical state (M5)
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on the touched paths
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
Agent registration and addressing (SPEC-09 and SPEC-09B).

## 11. Open questions
1. Can carbon-room's agent key archive and create rooms? `archive_room` needs "member of the room and write
   access". If agent keys are refused (403), keep the manual `ROOM_STEPS` path, and the README tells people to
   reset the room by hand.
2. `user_names` must be Mattermost usernames known to the bridge. Before M3 fills `username` in `people.yaml`,
   the list is empty, and people have to be added to the new room by hand.
