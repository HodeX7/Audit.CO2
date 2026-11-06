# SPEC-15 · App wiring, SwitchRoom, runner and end-to-end loop
Stories: P3-2.5, P3-8.2 (end-to-end test) · Branch: `p3-s15-app` · PR title: "P3-S15 (2.5, 8.2): app wiring, runner and room loop"
Depends on (must be merged): SPEC-02 through SPEC-14 (SPEC-08 with its §0 filled in) · Wave: 4 · Estimated session time: 2 h

> **Plan deviation (§5 S15, not §3).** `amain` returns an `int` exit code and gains test-only keyword arguments,
> and `Runtime` gains `start`, `wait_connected` and `stop`. Tests need to drive the runtime without signals.

## 1. Goal
Wire everything into one process:
- four sockets feed one dispatcher
- the dispatcher classifies with the acceptance rule and calls the handler table
- handlers post through a noise-guarded `SwitchRoom`, which uses each agent's ops client

`python -m carbon_room.room.run` starts it. It refuses to run if test doubles are loaded. An end-to-end test runs
a close and a thread reply through the fake Switch server, with no real Switch.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2 and all of §3
- `docs/spikes.md`
- Every module under `carbon_room/room/` and the P3 modules in `carbon_room/agents/`
- `tests/fakes/fake_switch.py`, `tests/fakes/fake_core.py` and `tests/fakes/fake_room.py`

## 3. Files
- Create `carbon_room/room/app.py`, `carbon_room/room/switch_room.py` and `carbon_room/room/run.py`
- Create `tests/room/test_app.py`, `tests/room/test_switch_room.py`, `tests/room/test_room_loop.py` and
  `tests/room/test_run_guard.py`

## 4. Public interface
```python
# app.py
Handler = Callable[[Context, RoomEvent, Intent, Actor], Awaitable[None]]
HANDLERS: dict[str, Handler]
def classify(event: RoomEvent, *, today: date, single_agent: bool) -> Intent
async def handle(ctx: Context, event: RoomEvent, intent: Intent) -> None
async def on_error(ctx: Context, event: RoomEvent, intent: Intent, exc: BaseException) -> None

# switch_room.py
class SwitchRoom:                                   # implements ports.Room
    def __init__(self, clients: Mapping[str, Any], *, single_agent: bool = False,
                 permalink_base: str | None = None, threads: bool = True) -> None

# run.py
@dataclass
class Runtime:
    ctx: Context
    dispatcher: Dispatcher
    connections: dict[str, AgentConnection]
    clients: dict[str, OpsClient]
    executor: concurrent.futures.ThreadPoolExecutor
    async def start(self) -> None                   # starts the dispatcher and connection tasks
    async def wait_connected(self, timeout: float) -> list[str]   # agents not connected in time ([] = all ok)
    async def stop(self) -> None
def build(settings: Settings, *, core: Any, transport: httpx.AsyncBaseTransport | None = None) -> Runtime
async def amain(settings: Settings, *, core: Any = None, transport: httpx.AsyncBaseTransport | None = None,
                connect_timeout: float = 30.0, stop_event: asyncio.Event | None = None) -> int
def main() -> int
```
`run.py` ends with `if __name__ == "__main__": raise SystemExit(main())`. When `amain`'s `core` is None, it uses
`carbon_room.core`, imported inside the function.

## 5. Behaviour

### app.py
1. **`HANDLERS`** maps all 11 non-ignore intent kinds:

   | Intent kind | Handler |
   |---|---|
   | `close.start` | `orchestrator.handle_close_start` |
   | `close.status` | `reports.handle_status` |
   | `close.resume` | `orchestrator.handle_resume` |
   | `close.publish` | `publish.handle_publish` |
   | `report.draft` | `publish.handle_draft` |
   | `report.trace` | `reports.handle_trace` |
   | `audit.verify` | `reports.handle_verify_audit` |
   | `help` | `reports.handle_help` |
   | `ask` | `ask.handle_ask` |
   | `gap.reply` | `resolution.handle_gap_reply` |
   | `gap.fallback` | `resolution.handle_gap_reply` |
2. **`classify`** is `intent = grammar.parse(event.body, in_thread=event.in_thread, today=today)`, followed by the
   acceptance rule:
   - `ignore` stays `ignore`.
   - `gap.reply` and `gap.fallback` are kept when `event.addressed or identity.is_known(event.sender)`.
   - Every other kind is kept when `single_agent`, or when `event.addressed and intent.target_agent ==
     event.receiving_agent`.
   - Anything not kept becomes `Intent("ignore", {}, None)`.
3. **`handle`** builds `actor = identity.actor_for(event.sender, event.sender_name)`, then awaits
   `HANDLERS[intent.kind](ctx, event, intent, actor)`.
4. **`on_error`** posts `errors.reply_for(exc, agent=intent.target_agent).text` as
   `intent.target_agent or "carbon-room"`, with `thread_id=event.thread_id or event.message_id`.

### switch_room.py
5. **`post(agent, text, *, thread_id=None, essential=True)`.** `essential` is ignored here; the noise guard sits
   on top.
   - **Threads off.** When `threads` is False and `thread_id` is set: `text = "↳ " + text`, `thread_id = None`,
     and log INFO `threads off: posting reply to <id> at top level`.
   - **Single agent.** In single-agent mode, the client is `clients["carbon-room"]`, and agents other than
     carbon-room get the prefix `f"[{AGENT_TITLES[agent]}] "` on the text, after any `↳ ` was added. So a
     threaded Watchdog line reads `"[Watchdog] ↳ Checking…"`.
   - **Normal mode.** The client is `clients[agent]`.
   - The method returns `await client.post(text, thread_id)`.
6. **`send_targeted(from_agent, to_agent, text)`.** In single-agent mode it logs INFO and does nothing. Otherwise it
   awaits `clients[from_agent].send_targeted(to_agent, text)`.
7. **`upsert_doc(agent, name, content)`** awaits `<client>.upsert_room_doc(name, content)`, choosing the client by
   the same rule as `post`.
8. **`link(message_id)`** is `f"{permalink_base}/{message_id}"` when a base is set, else `f"message {message_id}"`.
9. **`begin_close`** does nothing (DEBUG log).

### run.py
10. **`build(settings, *, core, transport)`.**
    1. `agents = ["carbon-room"]` in single-agent mode, else `list(AGENT_NAMES)`.
    2. For each agent, `cid = str(uuid.uuid4())`.
       - `OpsClient(settings.server, creds.agent_id, creds.api_key, connection_id=cid,
         room_id=settings.room_id, transport=transport, agent_ids={n: c.agent_id for n, c in
         settings.agents.items()})`
       - `AgentConnection(agent, creds.agent_id, creds.api_key, settings.server, [settings.room_id],
         filter, on_event=<set below>, connection_id=cid)`
       - `filter` is `"all"` for watchdog and in single-agent mode, `"addressed"` otherwise.
    3. `executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="core")`.
    4. `room = NoiseGuard(SwitchRoom(clients, single_agent=…, permalink_base=…, threads=…),
       max_posts=max_posts_from_config())`.
    5. **Downloads.** When `settings.attachments_mode == "download"` and `settings.media_path` is set,
       `download = lambda att: clients[watcher].download(att.mxc, settings.media_path)`, where `watcher` is
       watchdog, or carbon-room in single-agent mode. Otherwise `download = None`.
    6. `ctx = Context(core=AsyncCore(core, executor), room=room, display=identity.display,
       threads=settings.threads, attachments_mode=settings.attachments_mode, inbox_dir=settings.inbox_dir,
       download=download)`, then set `ctx.on_phase_end = functools.partial(hooks.after_phase, ctx)`.
    7. `own_ids = frozenset(c.agent_id for c in settings.agents.values())`.
    8. `dispatcher = Dispatcher(decode=lambda a, f: events.decode(f, a, own_ids), classify=lambda e:
       app.classify(e, today=ctx.today(), single_agent=settings.single_agent), handle=lambda e, i: app.handle(ctx,
       e, i), on_error=lambda e, i, x: app.on_error(ctx, e, i, x), room_id=settings.room_id)`. Every connection's
       `on_event` is `dispatcher.submit`.
    9. Nothing connects until `start()`.
11. **`Runtime` methods.**
    - **`start()`** creates tasks for `dispatcher.run()` and each `connection.run()`.
    - **`wait_connected(timeout)`** waits for every `connected` event and returns the names that didn't connect in
      time. A connection task that ended with `AuthError` counts as not connected immediately.
    - **`stop()`**:
      1. stops every connection
      2. `await dispatcher.stop()`
      3. `await client.aclose()` for each client
      4. `executor.shutdown(wait=False, cancel_futures=True)`
      5. awaits the tasks, swallowing their exceptions after logging them
12. **`amain(settings, *, core, transport, connect_timeout, stop_event)`.**
    1. `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`.
    2. `rt = build(...)`, then `await rt.start()`.
    3. `failed = await rt.wait_connected(connect_timeout)`. When it is non-empty, log ERROR
       `could not connect: <names>; run make doctor`, then `await rt.stop()` and return 2.
    4. `await orchestrator.resume_on_startup(rt.ctx)`. An exception here is logged, not fatal.
    5. Wait on `stop_event` (or a new event). When no `stop_event` was passed, install SIGINT and SIGTERM handlers
       that set it, via `loop.add_signal_handler`.
    6. `await rt.stop()`, log INFO `stopped`, and return 0.
13. **`main()`.**
    1. If any key of `sys.modules` equals `fakes` or `tests`, or starts with `fakes.` or `tests.`, print
       `refusing to run with test doubles loaded` to stderr and return 3.
    2. `settings = load_settings()`. A `ValueError` prints `carbon-room: <message>` to stderr and returns 1.
    3. Return `asyncio.run(amain(settings))`.
14. **Logging.** Never log keys. Each `AgentConnection` already logs its `connected agent=… rooms=… filter=…`
    line.

## 6. Test plan

**`tests/room/test_app.py`**

`ev(body, *, receiving, addressed, thread_id=None, sender="@switch-user-lead:test")` builds a `RoomEvent` with
`message_id="h-1"`. These tests use `people_config`, and `today=date(2026, 11, 5)`.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_classify_acceptance_matrix` (parametrized) | the rows below | `classify(ev(...), today=…, single_agent=s)` | `.kind` as listed [2] |
| `test_handlers_cover_every_intent_kind` | — | — | `set(HANDLERS) == {"close.start", "close.status", "close.resume", "close.publish", "report.draft", "report.trace", "audit.verify", "help", "ask", "gap.reply", "gap.fallback"}`, and `HANDLERS["gap.fallback"] is HANDLERS["gap.reply"]` [1] |
| `test_handle_builds_actor_from_sender` | monkeypatch `HANDLERS["close.status"]` with a recorder | `handle(ctx, ev("@carbon-room status", receiving="carbon-room", addressed=True), Intent("close.status", {}, "carbon-room"))` | the recorder got `Actor("human", "lead", "Sustainability Lead", "lead")` [3] |
| `test_on_error_replies_in_thread_as_target` | `FakeRoom` ctx | `on_error(ctx, ev("x", receiving="watchdog", addressed=True, thread_id="m-4"), Intent("gap.reply", {"text": "x"}, "watchdog"), ValueError("bad"))`; then the same with no `thread_id` and `Intent("ignore", {}, None)` and `LockHeld()` | the first post is watchdog, thread `m-4`, `"I couldn't do that: bad."`; the second is carbon-room, thread `h-1`, the LockHeld text [4] |

Acceptance matrix rows (`receiving`, `addressed`, body, `in thread`, `single_agent`, expected kind):

| # | receiving | addressed | body | thread | single | kind |
|---|---|---|---|---|---|---|
| 1 | carbon-room | T | `@carbon-room close October` | — | F | close.start |
| 2 | watchdog | F | `@carbon-room close October` | — | F | ignore |
| 3 | reporter | T | `@carbon-room close October` | — | F | ignore (wrong target) |
| 4 | carbon-room | F | `@carbon-room close October` | — | T | close.start |
| 5 | collector | T | `@collector what is HQ diesel?` | — | F | ask |
| 6 | watchdog | F | `pick a` | `m-4` | F | gap.reply (known sender) |
| 7 | watchdog | F | `pick a` (sender `@x:test`) | `m-4` | F | ignore (guest, not addressed) |
| 8 | watchdog | T | `pick a` (sender `@x:test`) | `m-4` | F | gap.reply |
| 9 | watchdog | F | `G-2 pick A` | — | F | gap.fallback |
| 10 | carbon-room | T | `@carbon-room G-2 pick A` | — | F | gap.fallback |
| 11 | watchdog | F | `hello everyone` | — | F | ignore |
| 12 | reporter | T | `@reporter trace S-1` | — | F | report.trace |
| 13 | carbon-room | T | `@reporter trace S-1` | — | F | ignore |

**`tests/room/test_switch_room.py`**

Use a stub client class defined in the test, which records `post(text, thread_id)` calls (returning `"srv-N"`),
`send_targeted` calls and `upsert_room_doc` calls. `clients` maps each agent name to its own stub.

| Test | Act | Assert |
|---|---|---|
| `test_switch_room_posts_via_right_client` | `post("watchdog", "x", thread_id="m-1")`, `post("reporter", "y")` | the watchdog stub got `("x", "m-1")` and the reporter stub got `("y", None)`; the returned ids come from the stubs [5] |
| `test_send_targeted_and_docs` | `send_targeted("carbon-room", "collector", "go")`; `upsert_doc("carbon-room", "close-board", "md")` | carbon-room's stub got `("collector", "go")` and `("close-board", "md")` [6, 7] |
| `test_single_agent_prefixes` | `single_agent=True`, with only a carbon-room stub | `post("watchdog", "x")`, `post("carbon-room", "y")`, `send_targeted("carbon-room", "collector", "go")` | the carbon-room stub got `"[Watchdog] x"` and `"y"`; no targeted call [5, 6] |
| `test_threads_off_prefix` | `threads=False` | `post("watchdog", "Checking…", thread_id="m-1")` | the stub got `("↳ Checking…", None)`; an INFO log. With single-agent as well: `"[Watchdog] ↳ Checking…"` [5] |
| `test_link_formats` | — | `SwitchRoom({}, permalink_base="http://mm/team/pl").link("abc")`, `SwitchRoom({}).link("abc")` | `"http://mm/team/pl/abc"`, `"message abc"` [8] |
| `test_switch_room_is_a_room` | — | — | `isinstance(SwitchRoom({}), Room)` |

**`tests/room/test_room_loop.py`** (the end-to-end test, under 20 s)

Arrange:
- `people_config`, `FakeSwitch(ping_interval=0.5, evict_after=5)` and `FakeCore()`.
- `settings = Settings(server=<fake url>, room_id="room-1", agents={n: AgentCreds(n, f"agent-{n}", f"key-{n}")
  for n in AGENT_NAMES}, threads=True, attachments_mode="inbox", single_agent=False, permalink_base=None,
  media_path=None)`.
- An `httpx.MockTransport` handler records every ops call as `(agent_id, op, body)`.
  - `post_message` is answered with `{"result": {ops.POST_ID_KEY: f"srv-{n}"}}`, where `n` counts up from 1. If
    `ops.POST_ID_KEY` is None, the test is skipped with the reason `"needs a post id key (spike S5)"`.
  - Every other op is answered with `{"result": {}}`.
- `rt = build(settings, core=fake_core, transport=mock)`, then `await rt.start()` and
  `assert await rt.wait_connected(5) == []`.

| Step | Act | Wait for |
|---|---|---|
| 1 | inject `FakeSwitch.message(body="@carbon-room close October", message_id="h-1", addressed=True)` to `agent-carbon-room`, and the same payload with `addressed=False` to `agent-watchdog` | a recorded `post_message` whose text (`body[ops.POST_TEXT_ARG]`) starts with `"I can't give a clean October 2026 total yet."` (timeout 10 s) |
| 2 | find G-2's root: the `srv-N` id returned for the post whose text starts with `"**G-2 "`. Inject `message(body="pick A", message_id="h-2", thread_id=<that id>, addressed=True)` to `agent-watchdog` | a `post_message` with text `"Resolved. G-2 is closed and the ledger is updated."` (timeout 5 s) |

Assert:
- `[c for c in fake_core.calls if c[0] == "start_close"]` has length 1, with `chat_message_id == "h-1"`.
- Exactly one `resolve` call, with `gap_id "G-2"`, `action "pick"`, `payload {"claim_id": "CL-0003"}`,
  `chat_message_id "h-2"` and `actor.id == "lead"`.
- The outcome post was made by `agent-watchdog`, and its body has `{ops.POST_THREAD_ARG: <G-2 root id>}` (skip
  this check if `POST_THREAD_ARG` is None).
- A `post_message` by `agent-carbon-room` with text `"Total moved 0.0 → 5.3 tCO2e, coverage 0% → 23%."`.
- Finally `await rt.stop()`.

| Test | Notes |
|---|---|
| `test_room_loop_close_then_thread_reply_resolves` | the steps and asserts above; the whole test runs inside `asyncio.wait_for(..., 20)` |
| `test_amain_returns_2_when_auth_fails` | `FakeSwitch(api_keys={"agent-carbon-room": "other"})`; `amain(settings, core=FakeCore(), transport=mock, connect_timeout=3, stop_event=asyncio.Event())` returns 2 within 5 s |
| `test_amain_stops_on_event` | start `amain(...)` with a `stop_event` as a task; once `fake_switch.connections` has 4 records with `connection_state` sent, set the event | the task returns 0 within 3 s |

**`tests/room/test_run_guard.py`**

| Test | Act | Assert |
|---|---|---|
| `test_main_refuses_with_fakes_loaded` | `import fakes.fake_core` (so it is in `sys.modules`); `main()` | returns 3; `"refusing to run with test doubles loaded"` is in `capsys` stderr; no settings were read (monkeypatch `run.load_settings` to fail the test if called) [13] |
| `test_run_module_does_not_import_fakes` | read `carbon_room/room/run.py` | no `fakes` or `tests` import [13] |

## 7. Fixtures and doubles
`FakeSwitch` (SPEC-07), `FakeCore` (SPEC-01), `httpx.MockTransport` and the `people_config` fixture. The ops
constants come from SPEC-08's `ops` module.

## 8. Manual check (real room)
- `make run` shows four `connected agent=… rooms=… filter=…` lines: `filter=all` for watchdog, `addressed` for the
  others.
- `@carbon-room status` with no close gets the `no_close` text, in a thread, from carbon-room only.
- `@reporter help` gets help from reporter only.
- Ctrl-C stops it within a few seconds and logs `stopped`.

## 9. Done when
- [ ] `make run` shows four connected agents, and a message to `@carbon-room` is received by that agent only
- [ ] The loop test passes in under 20 s with no real Switch
- [ ] Every test in §6 passes, and the full `pytest -q` passes (and `tests/room` takes under 20 s in total)
- [ ] ruff passes on `carbon_room/room carbon_room/agents tests/room tests/fakes` (P3 files)
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
The Makefile target (SPEC-16), real `people.yaml` ids (M3) and real-core behaviour (SPEC-18).

## 11. Open questions
None block execution beyond SPEC-08's §0. If spike S4 failed, set `CARBON_ROOM_SINGLE_AGENT=1`. The loop test
covers the four-socket path; single-agent mode is covered by `test_classify_acceptance_matrix` row 4 and
`test_single_agent_prefixes`.
