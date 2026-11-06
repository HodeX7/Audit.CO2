# SPEC-06 · Settings and event decoding
Stories: P3-2.2, plus env config · Branch: `p3-s06-settings-events` · PR title: "P3-S06 (2.2): settings and event decoding"
Depends on (must be merged): SPEC-01 · Wave: 1 · Estimated session time: 1 h

## 1. Goal
Read the room's environment variables into one typed `Settings` object, with a clear error that names every
missing variable. Decode a raw Switch frame into a `RoomEvent`, or None. Messages from our own four agents are
dropped, so the agents never react to themselves.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.5 (Domain frames, Control frames), §2, §3.2, §3.5 and §3.10
- `carbon_room/room/frames.py` and `carbon_room/room/ports.py` (SPEC-01)
- `.env.example`

## 3. Files
- Create `carbon_room/room/settings.py`
- Create `carbon_room/room/events.py`
- Create `tests/room/test_settings.py`
- Create `tests/room/test_events.py`
- Create the 11 frame fixtures in §7: `message_top.json`, `message_thread_reply.json`,
  `message_with_attachment.json`, `message_from_own_agent.json`, `message_no_id.json`, `command.json`,
  `room_join.json`, `ping.json`, `connection_state.json`, `evicted.json` and `message_bad_payload.json`, all in
  `tests/room/fixtures/frames/`
- Modify `.env.example`: append the block in §7 and keep the existing lines unchanged
- Modify `docs/switch-protocol-notes.md`: replace only the body of `## S06 events` (text in §7)

## 4. Public interface
```python
# settings.py
@dataclass(frozen=True)
class AgentCreds:
    name: str
    agent_id: str
    api_key: str            # field(repr=False): never in repr()

@dataclass(frozen=True)
class Settings:
    server: str
    room_id: str
    agents: dict[str, AgentCreds]
    threads: bool
    attachments_mode: str           # "download" | "inbox"
    single_agent: bool
    permalink_base: str | None
    media_path: str | None
    inbox_dir: Path = Path("data/inbox")

def env_name(agent: str, field: Literal["ID", "KEY"]) -> str
def load_settings(env: Mapping[str, str] | None = None) -> Settings
def missing(env: Mapping[str, str] | None = None, *, for_run: bool = True) -> list[str]
def read_env(env_file: str | Path = ".env") -> dict[str, str]

# events.py
@dataclass(frozen=True)
class Attachment:
    filename: str
    mimetype: str | None
    size: int | None
    mxc: str | None
    msgtype: str | None

@dataclass(frozen=True)
class RoomEvent:
    type: str                        # "message" | "room_join"
    room_id: str
    message_id: str
    thread_id: str | None
    sender: str
    sender_name: str
    body: str
    attachments: tuple[Attachment, ...]
    addressed: bool
    timestamp: int
    receiving_agent: str
    sequence: int
    @property
    def in_thread(self) -> bool       # thread_id is not None and thread_id != message_id

def decode(frame: dict, receiving_agent: str,
           own_sender_ids: frozenset[str] = frozenset()) -> RoomEvent | None
```

## 5. Behaviour

### settings.py
1. **`env_name(agent, field)`** is `"SWITCH_AGENT_" + agent.upper().replace("-", "_").replace(".", "_") + "_" +
   field`. For example, `("carbon-room", "ID")` gives `"SWITCH_AGENT_CARBON_ROOM_ID"`.
2. **`read_env(env_file)`** returns `{**dotenv_values(env_file), **os.environ}`, so the process environment wins
   over the file. A value of None from dotenv becomes `""`, and a missing file gives just `os.environ`.
3. **Default env.** When `env` is None, `load_settings` and `missing` use `read_env(".env")`.
4. **Empty values.** A variable counts as missing when it is absent, or when it is empty or whitespace-only after
   `strip()`. Every value is stripped before use.
5. **`missing(env, for_run=True)`** returns the missing names, in this order:
   1. `SWITCH_SERVER`
   2. `SWITCH_ROOM_ID`
   3. for each agent in `AGENT_NAMES` order, `env_name(agent, "ID")` then `env_name(agent, "KEY")`

   When `CARBON_ROOM_SINGLE_AGENT` parses true (rule 7), only carbon-room's two variables are required. With
   `for_run=False` (registration), it checks only `SWITCH_SERVER` and `SWITCH_REGISTRATION_KEY`, in that order.
6. **`load_settings(env)`.**
   - It raises `ValueError(f"missing settings: {', '.join(names)}")` when `missing(env)` is non-empty.
   - Otherwise it builds `Settings`. `server` is stripped of trailing `/`. `agents` holds an `AgentCreds` for each
     agent that has both an ID and a KEY, keyed by agent name.
7. **Flags.**
   - `CARBON_ROOM_THREADS` defaults to true. `CARBON_ROOM_SINGLE_AGENT` defaults to false.
   - When the variable is unset or empty, the default applies.
   - Otherwise the value is lowercased: `1`, `true`, `yes` or `on` mean true; `0`, `false`, `no` or `off` mean
     false.
   - Anything else raises `ValueError(f"{name} must be 1 or 0, got {value!r}")`.
8. **`CARBON_ROOM_ATTACHMENTS`** is `download` or `inbox` (lowercased), and defaults to `inbox`. Anything else
   raises `ValueError(f"CARBON_ROOM_ATTACHMENTS must be download or inbox, got {value!r}")`.
9. **Optional settings.** `MATTERMOST_PERMALINK_BASE` is stripped of trailing `/`, and empty means None.
   `SWITCH_MEDIA_PATH` is used as is, and empty means None. `inbox_dir` is always `Path("data/inbox")`.
10. **No secrets in output.** No error message, log line or `repr()` contains an API key or the registration key.

### events.py
11. **`decode(frame, receiving_agent, own_sender_ids)`** never raises. On any internal error it returns None and
    logs at DEBUG.
12. **Which kinds decode.** `kind = frames.frame_kind(frame)`. Only `message` and `room_join` decode;
    `command` (Switch handles bang commands), every control kind and None give None.
13. **Envelope.** `fields = frames.frame_fields(frame)`.
    - `payload = fields.get("payload")` must be a dict.
    - `room_id = fields.get("room_id")` must be a non-empty str.
    - `sequence = frames.sequence_of(frame)` must be an int.

    If any of these fails, decode returns None.
14. **`message` payload.**
    - `message_id` must be a non-empty str, else None.
    - `sender` and `sender_name` are strs, where a missing value or None becomes `""`.
    - `body` is a str, where None becomes `""`. Any other type gives None.
    - `thread_id` is a str or None, and `""` becomes None.
    - `addressed` is `payload.get("addressed") is True`.
    - `timestamp` is an int, defaulting to 0.
    - `attachments` holds one `Attachment` per dict in `payload["attachments"]`, in order; non-dict entries are
      skipped. Each one has `filename` (`""` if missing), `mimetype`, `size` (an int, else None), `mxc` and
      `msgtype`.
15. **Own agents.** A message is dropped (None) when `sender in own_sender_ids`, or when
    `sender_name.strip().lower()` is in `AGENT_NAMES`.
16. **`room_join`.** `sender = payload.get("member") or ""`, `sender_name = payload.get("member_name") or ""`,
    `message_id = f"join:{sequence}"`, `body = ""`, `thread_id = None`, `attachments = ()`,
    `addressed = False`, and `timestamp` is an int or 0. Own agents are dropped the same way as in rule 15.
17. **Other fields.** `receiving_agent` is the argument, and `type` is the kind.
18. **`in_thread`** is `thread_id is not None and thread_id != message_id`.

## 6. Test plan
`load(name)` reads `tests/room/fixtures/frames/<name>` as JSON. `ENV` is a full dict:
`SWITCH_SERVER="http://127.0.0.1:7777/"`, `SWITCH_ROOM_ID="room-1"`, and for each agent `<NAME>_ID="agent-<name>"`
and `<NAME>_KEY="key-<name>-secret"`.

**`tests/room/test_events.py`**

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_decode_top_level_message` | `message_top.json` | `decode(f, "carbon-room")` | `== RoomEvent("message", "room-1", "msg-top-1", None, "@switch-user-lead:test", "lead", "@carbon-room close October", (), True, 1793000000000, "carbon-room", 101)`; `in_thread is False` [12–14, 17, 18] |
| `test_decode_thread_reply` | `message_thread_reply.json` | `decode(f, "watchdog")` | `thread_id == "msg-root-1"`, `message_id == "msg-reply-1"`, `body == "pick a"`, `in_thread is True` [14, 18] |
| `test_thread_id_equal_to_message_id_is_not_in_thread` | a copy of top with `thread_id` set to its message id | decode | `in_thread is False` [18] |
| `test_decode_attachment_fields` | `message_with_attachment.json` | decode | `attachments == (Attachment("warehouse2_electricity_2026-10_actual.pdf", "application/pdf", 48213, "mxc://switch.local/abc123", "m.file"),)` and `body == ""` [14] |
| `test_decode_attachment_odd_entries` | top with `attachments: ["x", {"size": "12"}]` | decode | `(Attachment("", None, None, None, None),)` [14] |
| `test_decode_drops_own_agents_by_id_and_name` | `message_from_own_agent.json`; and top with `sender_name: " Reporter "` | `decode(f, "carbon-room")`; `decode(top, "carbon-room", frozenset({"@switch-user-lead:test"}))` | all None [15] |
| `test_decode_skips_command_and_control` | `command.json`, `ping.json`, `connection_state.json`, `evicted.json` | decode each | all None [12] |
| `test_decode_room_join` | `room_join.json` | `decode(f, "watchdog")` | `type == "room_join"`, `message_id == "join:106"`, `sender == "@switch-user-priya:test"`, `sender_name == "priya"`, `body == ""`, `addressed is False` [16] |
| `test_decode_malformed_returns_none` | `message_no_id.json`; `message_bad_payload.json`; top with `room_id` removed; top with `id` and `data.sequence` removed; top with `body: 5`; `{}`; `[]` | decode each | all None [11, 13, 14] |
| `test_decode_body_none_is_empty` | top with `body: null` | decode | `body == ""` [14] |
| `test_captured_frames_decode_without_error` | `glob("captured_*.json")` in the frames dir; `pytest.skip("no captured frames yet")` if none | decode each as `"watchdog"` | returns a `RoomEvent` or None, never raises [11] |
| `test_fixtures_are_labelled` | every `*.json` in the frames dir | load | has `_source` in `("docs", "captured")` |

**`tests/room/test_settings.py`**

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_env_name` | — | `env_name("carbon-room", "ID")`, `env_name("reporter", "KEY")` | `"SWITCH_AGENT_CARBON_ROOM_ID"`, `"SWITCH_AGENT_REPORTER_KEY"` [1] |
| `test_load_settings_reads_all_fields` | `ENV` plus `CARBON_ROOM_THREADS=0`, `CARBON_ROOM_ATTACHMENTS=download`, `MATTERMOST_PERMALINK_BASE="http://mm.local/team/pl/"`, `SWITCH_MEDIA_PATH="/agents/{agent_id}/media/{mxc}"` | `load_settings(env)` | `server == "http://127.0.0.1:7777"`, `room_id == "room-1"`, `agents["watchdog"] == AgentCreds("watchdog", "agent-watchdog", "key-watchdog-secret")`, 4 agents, `threads is False`, `attachments_mode == "download"`, `single_agent is False`, `permalink_base == "http://mm.local/team/pl"`, `media_path == "/agents/{agent_id}/media/{mxc}"`, `inbox_dir == Path("data/inbox")` [6–9] |
| `test_defaults` | `ENV` only | `load_settings(env)` | `threads is True`, `attachments_mode == "inbox"`, `single_agent is False`, `permalink_base is None`, `media_path is None` [7–9] |
| `test_load_settings_missing_lists_every_name` | `{}` | `load_settings({})` | `ValueError` with `str(e) == "missing settings: SWITCH_SERVER, SWITCH_ROOM_ID, SWITCH_AGENT_CARBON_ROOM_ID, SWITCH_AGENT_CARBON_ROOM_KEY, SWITCH_AGENT_COLLECTOR_ID, SWITCH_AGENT_COLLECTOR_KEY, SWITCH_AGENT_WATCHDOG_ID, SWITCH_AGENT_WATCHDOG_KEY, SWITCH_AGENT_REPORTER_ID, SWITCH_AGENT_REPORTER_KEY"` [5, 6] |
| `test_whitespace_counts_as_missing` | `ENV` with `SWITCH_ROOM_ID="  "` | `missing(env)` | `["SWITCH_ROOM_ID"]` [4] |
| `test_single_agent_needs_only_carbon_room` | `SWITCH_SERVER`, `SWITCH_ROOM_ID`, carbon-room ID and KEY, `CARBON_ROOM_SINGLE_AGENT=yes` | `missing(env)`, `load_settings(env)` | `[]`; `single_agent is True`; `list(agents) == ["carbon-room"]` [5, 6] |
| `test_missing_for_registration` | `{"SWITCH_SERVER": "http://x"}` | `missing(env, for_run=False)` | `["SWITCH_REGISTRATION_KEY"]` [5] |
| `test_bool_flags_parse` (parametrized) | `CARBON_ROOM_THREADS` set to each of `1, true, YES, on, 0, false, No, off, ""` | `load_settings` | `.threads` is `True, True, True, True, False, False, False, False, True` [7] |
| `test_bad_flag_and_mode_raise` | `CARBON_ROOM_THREADS="maybe"`; `CARBON_ROOM_ATTACHMENTS="ftp"` | `load_settings` | `ValueError("CARBON_ROOM_THREADS must be 1 or 0, got 'maybe'")`; `ValueError("CARBON_ROOM_ATTACHMENTS must be download or inbox, got 'ftp'")` [7, 8] |
| `test_read_env_file_and_environment` | tmp `.env` with `SWITCH_ROOM_ID=from-file` and `SWITCH_SERVER=http://file`; `monkeypatch.setenv("SWITCH_SERVER", "http://env")` | `read_env(path)` | `["SWITCH_ROOM_ID"] == "from-file"` and `["SWITCH_SERVER"] == "http://env"` [2] |
| `test_keys_not_in_repr_or_errors` | `ENV` | `repr(load_settings(ENV))`; and the `ValueError` from `load_settings({**ENV, "SWITCH_SERVER": ""})` | neither contains `"secret"` [10] |
| `test_env_example_lists_every_variable` | read `.env.example` | collect the names on lines matching `^([A-Z_]+)=` | they include `SWITCH_SERVER`, `SWITCH_ROOM_ID`, `SWITCH_REGISTRATION_KEY`, all 8 agent variables, `CARBON_ROOM_THREADS`, `CARBON_ROOM_ATTACHMENTS`, `CARBON_ROOM_SINGLE_AGENT`, `MATTERMOST_PERMALINK_BASE`, `SWITCH_MEDIA_PATH`, `ANTHROPIC_API_KEY` and `CARBON_ROOM_MODEL`; every line whose name ends `_KEY` has an empty value [§7] |

## 7. Fixtures and doubles

### Frame fixtures (exact, in `tests/room/fixtures/frames/`)
`message_top.json`
```json
{"_source": "docs", "event": "message", "id": 101,
 "data": {"type": "message", "room_id": "room-1", "bridge_id": null, "channel_type": "channel_public", "sequence": 101,
          "payload": {"addressed": true, "sender": "@switch-user-lead:test", "sender_name": "lead",
                      "message_id": "msg-top-1", "body": "@carbon-room close October", "timestamp": 1793000000000,
                      "thread_id": null, "attachments": []}}}
```
`message_thread_reply.json`
```json
{"_source": "docs", "event": "message", "id": 102,
 "data": {"type": "message", "room_id": "room-1", "bridge_id": null, "channel_type": "channel_public", "sequence": 102,
          "payload": {"addressed": true, "sender": "@switch-user-lead:test", "sender_name": "lead",
                      "message_id": "msg-reply-1", "body": "pick a", "timestamp": 1793000001000,
                      "thread_id": "msg-root-1", "attachments": []}}}
```
`message_with_attachment.json`
```json
{"_source": "docs", "event": "message", "id": 103,
 "data": {"type": "message", "room_id": "room-1", "bridge_id": null, "channel_type": "channel_public", "sequence": 103,
          "payload": {"addressed": true, "sender": "@switch-user-priya:test", "sender_name": "priya",
                      "message_id": "msg-att-1", "body": "", "timestamp": 1793000002000, "thread_id": "msg-root-1",
                      "attachments": [{"filename": "warehouse2_electricity_2026-10_actual.pdf",
                                       "mimetype": "application/pdf", "size": 48213,
                                       "mxc": "mxc://switch.local/abc123", "msgtype": "m.file"}]}}}
```
`message_from_own_agent.json`
```json
{"_source": "docs", "event": "message", "id": 104,
 "data": {"type": "message", "room_id": "room-1", "bridge_id": null, "channel_type": "channel_public", "sequence": 104,
          "payload": {"addressed": false, "sender": "@switch-agent-watchdog:test", "sender_name": "watchdog",
                      "message_id": "msg-own-1", "body": "**G-1 · PERIOD** …", "timestamp": 1793000003000,
                      "thread_id": null, "attachments": []}}}
```
`message_no_id.json`: the same as `message_top.json`, but with `"id": 107`, `"sequence": 107` and no
`message_id` key.

`message_bad_payload.json`
```json
{"_source": "docs", "event": "message", "id": 108,
 "data": {"type": "message", "room_id": "room-1", "sequence": 108, "payload": "not an object"}}
```
`command.json` (the ambiguous envelope: `event` is "message", `data.type` is "command")
```json
{"_source": "docs", "event": "message", "id": 105,
 "data": {"type": "command", "room_id": "room-1", "bridge_id": null, "channel_type": "channel_public", "sequence": 105,
          "payload": {"command": "status", "args": "", "user_id": "@switch-user-lead:test", "user_name": "lead",
                      "thread_id": null}}}
```
`room_join.json`
```json
{"_source": "docs", "event": "room_join", "id": 106,
 "data": {"type": "room_join", "room_id": "room-1", "bridge_id": null, "channel_type": "channel_public", "sequence": 106,
          "payload": {"member": "@switch-user-priya:test", "member_name": "priya", "timestamp": 1793000004000,
                      "listening": true}}}
```
`ping.json`
```json
{"_source": "docs", "type": "ping"}
```
`connection_state.json`
```json
{"_source": "docs", "type": "connection_state", "connection_id": "c-1", "agent_id": "agent-carbon-room",
 "generation": 3, "scope": "room", "filter": "addressed", "spawn_capable": false, "rooms": ["room-1"], "cursor": 100,
 "protocol": 6, "heartbeat_interval_seconds": 2, "server": "switch-local", "client": "carbon-room-python"}
```
`evicted.json`
```json
{"_source": "docs", "event": "evicted", "data": {"code": "heartbeat_lapsed", "reason": "no pong for 6 s"}}
```

### `.env.example`: append exactly this block after the existing lines
```
# ---- Switch room (P3). Run `make register` to fill the agent ids and keys. Never commit .env. ----
# Server address from Switch Console (not the Gateway web page).
SWITCH_SERVER=
# Id of the october-close room.
SWITCH_ROOM_ID=
# Gateway → API Keys → registration key. Only `make register` uses it.
SWITCH_REGISTRATION_KEY=
SWITCH_AGENT_CARBON_ROOM_ID=
SWITCH_AGENT_CARBON_ROOM_KEY=
SWITCH_AGENT_COLLECTOR_ID=
SWITCH_AGENT_COLLECTOR_KEY=
SWITCH_AGENT_WATCHDOG_ID=
SWITCH_AGENT_WATCHDOG_KEY=
SWITCH_AGENT_REPORTER_ID=
SWITCH_AGENT_REPORTER_KEY=
# 1 if agents can post into threads (spike S1), else 0.
CARBON_ROOM_THREADS=1
# download if attachments can be fetched (spike S2), else inbox (put files in data/inbox/).
CARBON_ROOM_ATTACHMENTS=inbox
# 1 if four sockets can't stay up (spike S4): one agent posts with [Watchdog] style prefixes.
CARBON_ROOM_SINGLE_AGENT=0
# Prefix for message links (spike S5). Leave empty to show "message <id>".
MATTERMOST_PERMALINK_BASE=
# Media download path with {agent_id} and {mxc} (spike S2). Leave empty if unknown.
SWITCH_MEDIA_PATH=
```

### `docs/switch-protocol-notes.md`: the body of `## S06 events`
Write these points under the heading, as plain bullets:
- the domain envelope shape
- the `message` and `room_join` payload fields that `decode` reads
- the rule that a domain kind in `data.type` wins over `event`
- what `decode` drops (commands, control frames, own agents, malformed frames)
- that the fixtures are documented shapes (`_source: docs`) until M2 captures real frames as
  `captured_*.json`

Keep it under 25 lines.

## 8. Manual check
After M2, put a captured frame (keys removed) in the fixtures as `captured_message_top.json`, then run
`pytest tests/room/test_events.py`.

## 9. Done when
- [ ] Fixtures for `message`, `command`, `room_join` and a control frame each decode, or are skipped, correctly
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Deciding what an event means (SPEC-02 and SPEC-15), and deduplication (SPEC-10).
- The P1 line `CARBON_ROOM_MODEL=claude-sonnet-4-5` in `.env.example`. It is P1 defect 6 (plan §1.3); leave it
  as it is.

## 11. Open questions
None block execution. The real envelope of `command` and `room_join` frames is unconfirmed until M2;
`command.json` deliberately covers the harder case.
