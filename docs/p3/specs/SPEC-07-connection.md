# SPEC-07 · Agent connection and fake Switch server
Stories: P3-2.1, P3-8.2 (server part) · Branch: `p3-s07-connection` · PR title: "P3-S07 (2.1, 8.2): agent connection and fake Switch"
Depends on (must be merged): SPEC-01 · Wave: 1 · Estimated session time: 2 h

> **Plan deviations (§5 S07, not §3)**
> 1. **Cursor from `connection_state`.** The cursor is adopted only when the client has none yet. The plan's
>    `max(cursor, state cursor)` loses events: if the state cursor is the server's head, every replayed event
>    after it would be skipped as a duplicate.
> 2. **`gap` frame.** It sets `cursor = resumed_at - 1`, not `resumed_at`. The docs don't say whether `resumed_at`
>    is the next event to be sent or the last one skipped. A cursor one lower can never lose an event, and the
>    dispatcher's message-id dedupe (SPEC-10) drops any duplicate. M2 should confirm the meaning.
> 3. **Fake additions.** The fake Switch gains `send_raw`, `refuse_next`, `api_keys`, `next_sequence` and
>    `wait_for_connections`, which the tests need.

## 1. Goal
One `AgentConnection` per agent holds a Switch WebSocket. It answers every `ping` straight from the read loop,
tracks the highest sequence, and hands domain frames to a synchronous callback. It reconnects with backoff and
resumes from its cursor without losing events. A small in-process fake Switch server lets all of this be tested
on localhost.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.5 (WebSocket, Domain frames, Control frames, Heartbeat and resume), §2,
  §3.2 and §3.12
- `carbon_room/room/frames.py` (SPEC-01)
- websockets 17: `websockets.asyncio.client.connect(uri, additional_headers=..., ping_interval=None,
  logger=...)` and `websockets.asyncio.server.serve(handler, "127.0.0.1", 0)`. In the handler,
  `ws.request.path` and `ws.request.headers` are available. `ConnectionClosed.rcvd.code` holds the close code.
  `websockets.exceptions.InvalidStatus.response.status_code` holds an HTTP rejection.

## 3. Files
- Create `carbon_room/room/connection.py`
- Create `tests/fakes/fake_switch.py`
- Create `tests/room/test_connection.py`
- Modify `docs/switch-protocol-notes.md`: replace only the body of `## S07 connection` (§7)

## 4. Public interface
```python
# connection.py
class AuthError(Exception): ...

def backoff_delays() -> Iterator[float]         # 1, 2, 4, 8, 16, 30, 30, 30, … (infinite)

class AgentConnection:
    def __init__(self, agent_name: str, agent_id: str, api_key: str, server: str, room_ids: list[str],
                 filter: Literal["all", "addressed"], on_event: Callable[[str, dict], None], *,
                 connection_id: str | None = None, client_version: str = "0.1.0",
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None
    agent_name: str
    connection_id: str               # given, or str(uuid4()); fixed for the object's life
    cursor: int | None
    generation: int | None
    connected: asyncio.Event         # set after each connection_state; cleared when the socket closes
    def url(self) -> str             # the WebSocket URL for the next attempt
    async def run(self) -> None      # returns after stop() or a final error; raises AuthError on 4401/HTTP 401
    async def stop(self) -> None
    def __repr__(self) -> str        # never contains api_key

# tests/fakes/fake_switch.py
@dataclass
class Record:
    agent_id: str
    query: dict[str, str]            # first value of each query parameter
    auth: str | None                 # the Authorization header as received
    pongs: list[tuple[float, int]]   # (time.monotonic(), cursor)
    pings_sent: list[float]          # time.monotonic() of each ping sent
    closed: bool = False

class FakeSwitch:
    def __init__(self, *, ping_interval: float = 2.0, evict_after: float = 6.0,
                 control_style: Literal["type", "event"] = "type",
                 api_keys: dict[str, str] | None = None) -> None
    connections: list[Record]
    next_sequence: int               # starts at 1; settable by tests
    async def start(self) -> str     # serves on 127.0.0.1:0; returns "http://127.0.0.1:<port>"
    async def stop(self) -> None
    async def inject(self, agent_id: str, payload: dict, *, room_id: str = "room-1",
                     kind: str = "message") -> int
    async def drop(self, agent_id: str, code: int = 1012) -> None
    async def evict(self, agent_id: str, code: str = "heartbeat_lapsed") -> None
    async def send_raw(self, agent_id: str, frame: dict) -> None
    def refuse_next(self, agent_id: str, code: int) -> None
    async def wait_for_connections(self, agent_id: str, n: int, timeout: float = 3.0) -> None
    @staticmethod
    def message(*, body: str, message_id: str, sender: str = "@switch-user-lead:test",
                sender_name: str = "lead", addressed: bool = True, thread_id: str | None = None,
                attachments: list[dict] | None = None, timestamp: int = 1793000000000) -> dict
```

## 5. Behaviour

### AgentConnection
1. **URL.**
   - `server` is stripped of trailing `/`. `http://` becomes `ws://` and `https://` becomes `wss://`, keeping any
     path prefix. The path `/agents/{agent_id}/connection/ws` is appended.
   - The query is `urlencode`d in this order: `connection_id`, `rooms` (comma-joined), `filter`,
     `client=carbon-room-python`, `client_version`, then `start_from=<cursor>` only when `cursor is not None`,
     then `expected_generation=<generation>` only when `generation is not None`.
2. **Connecting.**
   - Call `connect(url, additional_headers={"Authorization": f"Bearer {api_key}"}, ping_interval=None,
     logger=WIRE_LOG)`.
   - `WIRE_LOG = logging.getLogger("carbon_room.room.connection.wire")` has its level set to WARNING when the
     module loads, so websockets' DEBUG lines, which include headers, never run.
3. **First frame.**
   - It must be `connection_state` (by `frames.frame_kind`). Store `generation` when it is an int.
   - If `self.cursor is None` and the state's `cursor` is an int, set `self.cursor` to it (deviation 1).
   - Log one INFO line `connected agent=<name> rooms=<comma ids> filter=<filter>` on
     `carbon_room.room.connection`.
   - Set `connected` and restart the backoff sequence.
   - A first frame that isn't `connection_state` logs a WARNING, closes the socket, and counts as a disconnect
     (rule 5).
4. **Read loop.** Text frames are `json.loads`ed. Invalid JSON or a non-dict logs a WARNING and is skipped.
   Then, by kind:
   - **`ping`:** `await ws.send(frames.pong(self.cursor or 0))` before doing anything else.
   - **Domain kinds** (`message`, `command`, `room_join`):
     - `seq = frames.sequence_of(frame)`.
     - If `seq` is not None and `cursor` is not None and `seq <= cursor`, skip it (DEBUG log). This is a
       duplicate.
     - Otherwise set `cursor = seq` (when `seq` is not None) and call `on_event(agent_name, frame)`
       synchronously. It is never awaited. An exception from `on_event` is logged at ERROR and the loop
       continues.
   - **`gap`:** `resumed_at = frames.frame_fields(frame).get("resumed_at")`. When it is an int, set
     `cursor = resumed_at - 1` (deviation 2) and log INFO.
   - **`refused`:** log a WARNING with `status` and `detail`.
   - **`evicted`:**
     - Log a WARNING with `code` and `reason`.
     - For `taken_over` or `closed`, stop for good: close the socket, and `run()` returns.
     - Otherwise close the socket and reconnect (rule 5).
   - **`connection_state`** arriving later: update `generation` and log INFO. `subscription_changed` and
     `room_released` log INFO. Anything else, including None, is ignored with a DEBUG log.
5. **Disconnects and close codes.**
   - **4401, or an HTTP 401/403 at the handshake** (`InvalidStatus`): `run()` raises
     `AuthError(f"Switch rejected the key for {agent_name}")`. There is no retry.
   - **4400, 4403 or 4409:** log an ERROR with the code, and `run()` returns. There is no retry.
   - **Anything else** (1000, 1001, 1011, 1012, no close frame, `OSError`, `TimeoutError`, other
     `InvalidStatus` or `InvalidHandshake`):
     - Clear `connected`.
     - `await self._sleep(next(backoff))`, which `stop()` can interrupt.
     - Reconnect with the same `connection_id`, `start_from=cursor` and `expected_generation` (rule 1).
6. **`backoff_delays()`** yields `1, 2, 4, 8, 16`, then `30` forever. Each successful `connection_state` starts a
   fresh sequence.
7. **`stop()`.**
   - Sets a stop flag and closes the current socket, if any.
   - Interrupts a pending backoff sleep: wait on `sleep` and an internal stop event with `asyncio.wait(...,
     FIRST_COMPLETED)`.
   - `run()` returns within 1 s of `stop()`, whether it was reading or waiting to reconnect. Calling `stop()`
     before `run()` makes `run()` return at once.
8. **Secrets.** The key is never logged, never in an exception message, and never in `repr()`. `__repr__` is
   `f"AgentConnection({agent_name!r}, rooms={room_ids!r}, filter={filter!r})"`.

### FakeSwitch
9. **Serving.** `start()` serves `websockets.asyncio.server.serve(handler, "127.0.0.1", 0)` and returns
   `http://127.0.0.1:<port>`. `stop()` closes every connection and the server.
10. **On each connection:**
    1. **Path.** Parse `/agents/{agent_id}/connection/ws?…`. A different path closes with 4400.
    2. **Record.** Append a `Record` built from the path, the query and the `Authorization` header.
    3. **Auth.**
       - No `Bearer ` header: close with code 4401 and no other frame.
       - When `api_keys` is set and `api_keys.get(agent_id) != <bearer token>`: close with 4401.
    4. **Refusal.** If `refuse_next` was called for this agent, close once with that code and clear the entry.
    5. **State.** Send `connection_state`. `generation` is the count of opens for this agent so far. `cursor` is
       `int(start_from)` when the query has it, else `next_sequence - 1`. The frame also carries
       `connection_id`, `agent_id`, `rooms` (a list from the query), `filter` and
       `heartbeat_interval_seconds=ping_interval`.
    6. **Replay.** When the query has `start_from`, send the agent's buffered events with
       `sequence > start_from`, in order. Without it, replay nothing.
    7. **Heartbeat.** Send a ping every `ping_interval` seconds, recording `pings_sent`. If no pong has arrived
       for `evict_after` seconds (counted from the open, then from the last pong), send `evicted` with
       `{"code": "heartbeat_lapsed", "reason": "no pong"}` and close with 1000.
    8. **Pongs.** Record each `{"type": "pong", "cursor": n}` received as `(time.monotonic(), n)`. Ignore any
       other client frame.
11. **Control frames.**
    - With `control_style="type"` they are sent as `{"type": <kind>, **fields}`.
    - With `"event"` they are sent as `{"event": <kind>, "data": {**fields}}`.
    - This applies to `connection_state`, `ping`, `evicted` and anything sent with `send_raw`, which is sent
      unchanged.
12. **`inject(agent_id, payload, *, room_id, kind)`.**
    - Assigns `seq = next_sequence`, then increments it.
    - Builds `{"event": kind, "data": {"type": kind, "room_id": room_id, "bridge_id": None, "channel_type":
      "channel_public", "payload": payload, "sequence": seq}, "id": seq}`.
    - Buffers the frame for `agent_id`, sends it now if that agent has an open connection, and returns `seq`.
13. **Server-side actions.**
    - `drop(agent_id, code)` closes that agent's open socket with `code`.
    - `evict(agent_id, code)` sends `evicted` with `{"code": code, "reason": "test"}`, then closes with 1000.
    - `send_raw(agent_id, frame)` sends `json.dumps(frame)` to the agent's open socket.
    - All three do nothing if the agent has no open socket.
14. **`wait_for_connections(agent_id, n, timeout)`** returns once `n` Records exist for `agent_id` and the newest
    has sent `connection_state`. Otherwise it raises `TimeoutError`.
15. **`message(...)`** returns the `message` payload dict: `addressed`, `sender`, `sender_name`, `message_id`,
    `body`, `timestamp`, `thread_id` and `attachments` (or `[]`).

## 6. Test plan
Every test uses real localhost sockets: `FakeSwitch(ping_interval=0.2, evict_after=0.6)`, unless the test says
otherwise. Each test is an `async def` body run with `asyncio.run(...)` and wrapped in `asyncio.wait_for(...,
5)`. The shared helper `make_conn(server, agent_id="agent-cr", key="sk-test-secret", filter="addressed",
received=None, **kw)` builds an `AgentConnection("carbon-room", agent_id, key, server, ["room-1"], filter,
on_event=lambda a, f: received.append((a, f)), sleep=fast_sleep, **kw)`. `fast_sleep(d)` records `d` in a list and
awaits `asyncio.sleep(0.01)`. Each test runs `conn.run()` as a task, awaits `conn.stop()` at the end, and then
awaits the task.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_url_scheme_and_query` | `AgentConnection(... server="https://h.example/base/", ...)` with `connection_id="c-1"`; then set `cursor=5` and `generation=2` | `url()` twice | first `"wss://h.example/base/agents/agent-cr/connection/ws?connection_id=c-1&rooms=room-1&filter=addressed&client=carbon-room-python&client_version=0.1.0"`; then the same with `&start_from=5&expected_generation=2` appended [1] |
| `test_sends_auth_and_query` | fake started | run until `connected` | `connections[0].auth == "Bearer sk-test-secret"`; query has `rooms == "room-1"`, `filter == "addressed"`, `client == "carbon-room-python"` and no `start_from` [1, 2, 10] |
| `test_first_frame_sets_generation_and_cursor` | `next_sequence = 8` before connecting | run until `connected` | `conn.generation == 1`, `conn.cursor == 7` [3] |
| `test_pong_within_200ms_even_while_worker_thread_sleeps` | connected; start `loop.run_in_executor(None, time.sleep, 1.0)` | wait 1.0 s | at least 4 pings sent; for every ping except the last, a pong was recorded within 0.2 s after it [4] |
| `test_pong_cursor_is_highest_sequence` | connected | inject 3 messages, wait 0.5 s | the latest pong cursor equals the third `inject` return value [4] |
| `test_events_delivered_in_order_and_duplicates_skipped` | connected | inject `m1`, `m2`; `send_raw` the `m1` frame again (same `id`); inject `m3` | `received` holds frames with sequences `[s1, s2, s3]` exactly, in that order, each tagged `"carbon-room"` [4] |
| `test_server_drop_reconnects_with_same_id_and_cursor_no_loss` | connected | inject 3; `drop(code=1012)`; inject 2 while disconnected; `wait_for_connections("agent-cr", 2)`; wait 0.3 s | 5 distinct sequences received, once each, in order; `connections[1].query["connection_id"] == connections[0].query["connection_id"]`; `connections[1].query["start_from"] == str(s3)`; `connections[1].query["expected_generation"] == "1"`; `fast_sleep` recorded `[1]` [5] |
| `test_evicted_heartbeat_reconnects` | connected | `evict(code="heartbeat_lapsed")`; wait for 2 connections | reconnected; a WARNING log contains `heartbeat_lapsed` [4, 5] |
| `test_server_evicts_when_client_never_pongs` | `FakeSwitch(ping_interval=0.1, evict_after=0.3)`; a raw `websockets` client that connects with a Bearer header and never pongs | read frames for 1 s | `connection_state`, then pings, then `evicted` with code `heartbeat_lapsed`, then close code 1000 [10] |
| `test_evicted_taken_over_stops` | connected | `evict(code="taken_over")` | the `run()` task finishes within 1 s with no exception; only 1 connection recorded [4] |
| `test_evicted_closed_stops` | connected | `evict(code="closed")` | same as above [4] |
| `test_4401_raises_auth_error_without_retry` | `FakeSwitch(api_keys={"agent-cr": "right"})`; key `"wrong"` | `await run()` | raises `AuthError`; 1 connection recorded; `fast_sleep` never called [5] |
| `test_4403_stops_without_retry` | `refuse_next("agent-cr", 4403)` | `await run()` | returns None within 1 s; 1 connection; an ERROR log contains `4403` [5] |
| `test_gap_frame_moves_cursor` | connected; `next_sequence = 50` | `send_raw({"type": "gap", "from_sequence": 3, "resumed_at": 50, "resumed_position": 0, "rooms": ["room-1"], "all_rooms": False, "reason": "retention"})`; then inject one message (seq 50) | `conn.cursor == 50`; that message was delivered [4] |
| `test_both_control_styles` (parametrized `"type"`, `"event"`) | `FakeSwitch(control_style=style, …)` | connect, inject 1, wait 0.5 s | connected; 1 event received; pongs recorded [3, 4, 11] |
| `test_first_frame_not_state_reconnects` | a minimal `websockets.asyncio.server.serve` handler defined in the test. On its first connection it sends `{"type": "ping"}` and waits; on later connections it sends `{"type": "connection_state", "generation": 1, "cursor": 0}` and keeps the socket open. It counts connections | run until `connected` | the handler counted 2 connections; a WARNING was logged [3] |
| `test_on_event_exception_is_logged_and_loop_continues` | `on_event` raises on its first call | inject 2 | the second event is still delivered; an ERROR log; still connected [4] |
| `test_backoff_sequence` | — | `list(itertools.islice(backoff_delays(), 8))` | `[1, 2, 4, 8, 16, 30, 30, 30]` [6] |
| `test_backoff_resets_after_connect` | connected | `drop`, wait for 2 connections, `drop` again, wait for 3 | `fast_sleep` delays are `[1, 1]` [6] |
| `test_stop_returns_quickly` | connected | `t0`; `await stop()`; await the task | elapsed < 1.0 s [7] |
| `test_stop_during_backoff` | connected; real `asyncio.sleep` as `sleep`; `await fake.stop()` (server gone) | wait 0.3 s, `await stop()` | the task finishes within 1 s [7] |
| `test_key_never_logged` | `caplog.set_level(logging.DEBUG)` | connect, inject 1, drop, reconnect, then a separate 4401 run | `"sk-test-secret"` not in `caplog.text`; not in `repr(conn)`; not in `str(AuthError)` [2, 8] |

The whole module finishes in under 15 s.

## 7. Fixtures and doubles
- `tests/fakes/fake_switch.py` is defined above. It lives only under `tests/`.
- `docs/switch-protocol-notes.md`, the body of `## S07 connection`, at most 25 lines:
  - the URL and query parameters
  - the auth header
  - the first frame
  - the ping and pong rule
  - cursor handling, including both deviations and why
  - close codes and eviction codes, with what the client does for each
  - the backoff sequence
  - what M2 must confirm: the `gap` semantics, the control frame envelope, and whether a handshake auth failure
    is HTTP 401 or close code 4401

## 8. Manual check
After M1 and S09: run `python -c` with a single `AgentConnection` against the real server for 60 s. You should
see one `connected …` INFO line and no `evicted`. M2's S4 spike covers four sockets.

## 9. Done when
- [ ] Against the fake Switch server, pongs are sent within 200 ms
- [ ] A server-side close leads to a reconnect without lost events
- [ ] Every test in §6 passes; the module runs in under 15 s; the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room tests/fakes`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Decoding events (SPEC-06), queueing them (SPEC-10) and ops calls (SPEC-08).
- The end-to-end loop test (SPEC-15).

## 11. Open questions
None block execution. To confirm in M2 and record in `docs/spikes.md`: the meaning of `resumed_at`, the control
frame envelope, and whether a bad key is rejected at the HTTP handshake or with close code 4401. All three are
handled either way.
