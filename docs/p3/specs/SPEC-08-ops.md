# SPEC-08 · Ops client
Stories: P3-2.3 · Branch: `p3-s08-ops` · PR title: "P3-S08 (2.3): ops client"
Depends on (must be merged): SPEC-06 · Wave: 2 · Estimated session time: 1.5 h

> **Ready.** §0 is filled in from the input schemas and descriptions in `docs/switch-ops.json` (on `main`). Spikes
> S1, S5 and S6 have **not** yet been run against the live server. §8 is that live check: run it after merge,
> and if a value turns out wrong, change one constant in a follow-up PR.

> **Contract change (plan §3.11, edited in the same change as this spec)**
> 1. `ops.py` exports the §0 constants. SPEC-15's end-to-end test reads them to fake the server's responses.
> 2. `OpsClient.__init__` gains `agent_ids: Mapping[str, str] | None = None` (agent name → Switch id). It is
>    accepted and stored; with `TARGETED_TO_KIND = "names"` it is not used yet.
> 3. **New method `connect_room()`.** `post_message`'s docs say messages go to "the room this session is
>    connected to via `connect_to_room`". The client calls it once, lazily, before its first room-scoped op.

## 0. Switch inputs (from `docs/switch-ops.json`)

| Constant | Value | Source |
|---|---|---|
| `POST_TEXT_ARG` | `"body"` | `post_message` schema (required) |
| `POST_ROOM_ARG` | `None` | docs: "The room is implicit … there is no `room_id` parameter" |
| `POST_THREAD_ARG` | `"thread_id"` | schema; any message id in the thread works ("normalised to the thread root"). **S1 live check pending** |
| `POST_ID_KEY` | `"event_id"` | docs: returns `{"event_id": …}`. **S5 live check pending:** it must equal the `message_id` and `thread_id` seen in WebSocket frames |
| `TARGETED_TO_ARG` | `"target_names"` | `send_targeted_message` schema |
| `TARGETED_TO_KIND` | `"names"` | docs: "the `name` field from list_participants, not ids", a list |
| `TARGETED_TEXT_ARG` | `"body"` | schema (required) |
| `READ_LIMIT_ARG` | `"limit"` | `read_context` schema (default 50) |
| `READ_THREADS_KEY` | `"threads"` | docs: `{"threads": [{"root": <entry>, "replies": [<entry>…]}], "truncated", "oldest_timestamp"}` |
| `CONTEXT_ID_KEY`, `CONTEXT_BODY_KEY`, `CONTEXT_SENDER_KEY`, `CONTEXT_TIME_KEY`, `CONTEXT_KIND_KEY` | `"id"`, `"body"`, `"sender"`, `"timestamp"`, `"kind"` | docs: `<entry>` is `{"id", "kind", "sender", "sender_name", "body", "timestamp", "attachments"}` |
| `DOCS_SUPPORTED` | `True` | docs: "visible to all participants … human users can delete it from the room UI". **S6 live check pending** |
| `DOC_NAME_ARG`, `DOC_CONTENT_ARG` | `"name"`, `"content"` | `create_room_document` schema |
| `DOC_CREATE_EXTRA` | `{"description": "Live close figures and open gaps.", "instructions": "Status board kept up to date by carbon-room. Read it; don't edit it."}` | `description` and `instructions` are required by the schema |
| `DOC_ID_ARG`, `DOC_ID_KEY` | `"document_id"`, `"document_id"` | `update_room_document` requires `document_id`; create returns `{"document_id": …}` |
| `CONNECT_BEFORE_ROOM_OPS` | `True` | `post_message` and `list_participants` docs say the session must be connected to a room first |

The op names are fixed: `POST_MESSAGE = "post_message"`, `SEND_TARGETED = "send_targeted_message"`,
`READ_CONTEXT = "read_context"`, `CREATE_DOC = "create_room_document"`, `UPDATE_DOC = "update_room_document"` and
`CONNECT_ROOM = "connect_to_room"`.

## 1. Goal
An async `httpx` client for Switch ops, one per agent. It calls any op with the right headers and unwraps the
result, and it maps HTTP errors to one `SwitchError` with the server's detail. It connects its session to the
room once, then offers the helpers the room needs: post (top level or in a thread), targeted message, read
context, upsert a room document, and download attachment bytes.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.5 (Ops, Media), §2 and §3.11
- `docs/switch-ops.json`: the `post_message`, `send_targeted_message`, `read_context`, `connect_to_room`,
  `create_room_document` and `update_room_document` entries
- `carbon_room/room/settings.py` (SPEC-06)

## 3. Files
- Create `carbon_room/room/ops.py`
- Create `tests/room/test_ops.py`
- Modify `docs/switch-protocol-notes.md`: replace only the body of `## S08 ops`

## 4. Public interface
```python
# the §0 constants and the six op names, at module level

class SwitchError(Exception):
    def __init__(self, status: int | None, op: str, detail: str) -> None
    status: int | None
    op: str
    detail: str
    # str(e) == f"{op} failed ({status}): {detail}", or f"{op} failed: {detail}" when status is None

class OpsClient:
    def __init__(self, server: str, agent_id: str, api_key: str, *, connection_id: str | None = None,
                 room_id: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 10.0, agent_ids: Mapping[str, str] | None = None) -> None
    connection_id: str | None
    async def list_ops(self) -> dict[str, dict]
    async def call(self, op: str, args: dict | None = None) -> Any
    async def connect_room(self) -> dict                 # connect_to_room result; cached
    async def post(self, text: str, thread_id: str | None = None) -> str
    async def send_targeted(self, to_agent: str, text: str) -> Any
    async def read_context(self, limit: int = 20) -> list[dict]
    async def upsert_room_doc(self, name: str, content: str) -> bool
    async def download(self, mxc: str, path_template: str) -> bytes
    async def aclose(self) -> None
    def __repr__(self) -> str                            # never contains api_key
```

## 5. Behaviour
1. **Client.** One `httpx.AsyncClient(base_url=server.rstrip("/"), transport=transport, timeout=timeout)` per
   `OpsClient`.
2. **`call(op, args)`.**
   - Sends `POST /agents/{agent_id}/ops/{op}` with `json=args or {}` and the headers
     `Authorization: Bearer <key>` and `Content-Type: application/json`, plus `X-Switch-Connection-Id:
     <connection_id>` when the attribute is set at call time.
   - A 2xx response returns `response.json()["result"]`.
   - A 2xx response with no `result` key raises `SwitchError(status, op, "response has no result")`.
3. **Errors.**
   - A status of 400 or above raises `SwitchError(status, op, detail)`.
   - `detail` is the JSON body's `detail` when it is a str, `json.dumps` of it when it is any other non-None
     value, and otherwise the body text cut to 300 characters.
   - `httpx.TransportError` raises `SwitchError(None, op, str(exc) or type(exc).__name__)`.
4. **`list_ops()`** sends `GET /agents/{agent_id}/ops` with the same auth and returns `json()["operations"]`. The
   result is cached after the first success.
5. **`connect_room()`.**
   - If `room_id` or `connection_id` is None, raise `SwitchError(None, "connect_to_room", "no room or connection
     id")`.
   - Otherwise `result = await call("connect_to_room", {"room_id": room_id, "include_general_instructions":
     False})`, which sends the connection-id header.
   - When `result.get("warning")` is truthy, log a WARNING `connect_to_room: <warning>`.
   - Cache and return `result`. A second call returns the cache without a request.
6. **Room-scoped ops.** `post`, `send_targeted`, `read_context` and `upsert_room_doc` first `await
   self.connect_room()` when `CONNECT_BEFORE_ROOM_OPS` is True. A failure there propagates.
7. **`post(text, thread_id=None)`.**
   - The args are `{POST_TEXT_ARG: text}`, plus `{POST_ROOM_ARG: room_id}` when `POST_ROOM_ARG` and `room_id`
     are both set.
   - With `thread_id`: if `POST_THREAD_ARG is None`, raise `SwitchError(None, "post_message", "threads
     unsupported")` before any call. Otherwise add `{POST_THREAD_ARG: thread_id}`.
   - The id is `result[POST_ID_KEY]` when `POST_ID_KEY` is set and `result` is a dict holding a non-empty str or
     int (an int becomes a str).
   - Otherwise, fall back: `msgs = await read_context(10)` and take the `message_id` of the **last** entry, in
     rule-9 order, whose `body == text`.
   - If there is still no id, raise `SwitchError(None, "post_message", "no message id returned")`.
8. **`send_targeted(to_agent, text)`.**
   - The target value depends on `TARGETED_TO_KIND`: `name` gives `to_agent`; `id` gives `agent_ids[to_agent]`;
     `names` gives `[to_agent]`; `ids` gives `[agent_ids[to_agent]]`.
   - A missing `agent_ids` entry raises `SwitchError(None, "send_targeted_message", f"no Switch id for
     {to_agent}")`.
   - The args are `{TARGETED_TO_ARG: value, TARGETED_TEXT_ARG: text}`.
   - When `"not_permitted"` appears anywhere in `json.dumps(result)`, log a WARNING `send_targeted to <agent> was
     not permitted`. It doesn't raise. The real shape is `{"event_id", "target_statuses": {name: status}}`.
   - The result is returned.
9. **`read_context(limit=20)`.**
   - `result = await call(READ_CONTEXT, {READ_LIMIT_ARG: limit})`.
   - For each group in `result[READ_THREADS_KEY]`, emit the `root` entry and then each entry in `replies`, in
     order. Keep only entries whose `CONTEXT_KIND_KEY` value is `"message"`, or that have no kind.
   - Normalise each entry to `{"message_id": e[CONTEXT_ID_KEY], "body": e.get(CONTEXT_BODY_KEY) or "",
     "sender": e.get(CONTEXT_SENDER_KEY) or "", "thread_id": None for a root, or the root's id for a reply,
     "timestamp": e.get(CONTEXT_TIME_KEY) or 0}`.
   - Return them sorted by `timestamp`, ascending. The sort is stable, so ties keep emission order. The result is
     oldest first.
   - A result without `READ_THREADS_KEY` gives `[]`.
10. **`upsert_room_doc(name, content)`.**
    1. If `DOCS_SUPPORTED` is False, return False with no call.
    2. **Find the id.** Use a per-client `name → document_id` cache. When it has no entry for `name`, look in
       `(await self.connect_room()).get("documents") or []` for an entry whose `name` equals `name`, and cache
       its `id`. This lets a restarted process find the board it created before.
    3. **Update.** When an id is known, call `UPDATE_DOC` with `{DOC_ID_ARG: id, DOC_CONTENT_ARG: content}` and
       return True. If the update raises a `SwitchError` with status 404, drop the cached id and continue at
       step 4.
    4. **Create.** Call `CREATE_DOC` with `{DOC_NAME_ARG: name, DOC_CONTENT_ARG: content, **DOC_CREATE_EXTRA}`.
       Cache `result[DOC_ID_KEY]` and return True.
    5. A create that fails with status 409, or with a detail containing `exist` (case-insensitive), logs a
       WARNING `room document <name> exists but its id is unknown` and returns False. A create result without
       `DOC_ID_KEY` logs a WARNING and returns False.
    6. Any other `SwitchError` propagates.
11. **`download(mxc, path_template)`.**
    - The template's fields are `{agent_id}`, `{mxc}` (`urllib.parse.quote(mxc, safe="")`), `{server_name}` (the
      mxc host) and `{media_id}` (the last path segment of the mxc). `str.format` fills them.
    - Sends `GET` to the result with the auth header and returns `response.content`.
    - A status of 400 or above raises `SwitchError(status, "download", detail)`.
12. **`aclose()`** closes the httpx client.
13. **Secrets.** No log line, exception or `repr()` contains the API key or the `Authorization` header.
    `__repr__` is `f"OpsClient(agent_id={agent_id!r})"`.

## 6. Test plan
Every test uses `httpx.MockTransport(handler)`, where `handler` records each `httpx.Request` and answers by path.
Unless a test says otherwise, `connect_to_room` answers 200
`{"result": {"room_id": "room-1", "documents": [], "warning": None}}`. Build the client with
`OpsClient("http://sw.test", "agent-cr", "sk-test-secret", connection_id="conn-1", room_id="room-1",
transport=mock)`. Each test is an `async def` run with `asyncio.run`. Expected bodies use **literal names** from §0
(`"body"`, `"thread_id"` and so on), not the constants, so a wrong constant fails a test. Fallback cases use
`monkeypatch.setattr(ops, "POST_ID_KEY", None)` and the like. `ops_after_connect(reqs)` drops the
`connect_to_room` request from the recorded list.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_call_headers_and_unwrapped_body` | 200 `{"result": {"ok": 1}}` | `call("whoami", {"a": 1})` | method POST; URL `http://sw.test/agents/agent-cr/ops/whoami`; headers `authorization == "Bearer sk-test-secret"`, `content-type == "application/json"`, `x-switch-connection-id == "conn-1"`; `json.loads(body) == {"a": 1}` [2] |
| `test_call_without_connection_id_omits_header` | `client.connection_id = None` | `call("x")` | no `x-switch-connection-id` header; body `{}` [2] |
| `test_result_unwrapped` | 200 `{"result": [1, 2]}`; then 200 `{"nope": 1}` | `call("x")` twice | `[1, 2]`; then `SwitchError` with detail `"response has no result"` [2] |
| `test_error_mapping_400_403_404_409` (parametrized) | status `s` with `{"detail": "bad thing"}` for 400, 403, 404 and 409; then 500 with text body `"x" * 400` | `call("op1")` | `SwitchError` with `.status == s`, `.op == "op1"`, `.detail == "bad thing"`, `str(e) == f"op1 failed ({s}): bad thing"`; for 500, `len(.detail) == 300` [3] |
| `test_error_detail_non_string` | 400 `{"detail": [{"loc": ["x"]}]}` | `call("op1")` | `.detail == json.dumps([{"loc": ["x"]}])` [3] |
| `test_network_error_maps_to_switch_error` | handler raises `httpx.ConnectError("refused")` | `call("op1")` | `SwitchError` with status None and `"refused"` in detail [3] |
| `test_list_ops_cached` | 200 `{"operations": {"post_message": {"description": "d", "input_schema": {}}}}` | `list_ops()` twice | the same dict; 1 request, `GET /agents/agent-cr/ops` [4] |
| `test_connect_room_once_and_warns` | `connect_to_room` returns `{"result": {"warning": "evicted session x", "documents": []}}`; caplog | `post("a")`, `post("b")` | exactly one `connect_to_room` request, with body `{"room_id": "room-1", "include_general_instructions": False}` and the connection-id header; a WARNING contains `evicted session x` [5, 6] |
| `test_connect_room_needs_ids` | `connection_id=None` | `post("a")` | `SwitchError` with detail `"no room or connection id"`; 0 requests [5] |
| `test_post_top_level_and_thread_args` | `post_message` returns `{"result": {"event_id": "$e1"}}` | `post("hi")`; `post("re", thread_id="$root")` | the `post_message` bodies are `{"body": "hi"}` and `{"body": "re", "thread_id": "$root"}`; the first returns `"$e1"` [7] |
| `test_post_returns_int_id_as_str` | result `{"event_id": 42}` | `post("hi")` | `"42"` [7] |
| `test_post_message_id_fallback_read_context` | `POST_ID_KEY = None`; `post_message` returns `{"result": {}}`; `read_context` returns `{"result": {"threads": [{"root": {"id": "a", "kind": "message", "body": "hi", "sender": "s", "timestamp": 1}, "replies": []}, {"root": {"id": "b", "kind": "message", "body": "other", "sender": "s", "timestamp": 2}, "replies": [{"id": "c", "kind": "message", "body": "hi", "sender": "s", "timestamp": 3}]}], "truncated": False}}` | `post("hi")` | `"c"`; the `read_context` request body is `{"limit": 10}` [7, 9] |
| `test_post_no_id_raises` | `POST_ID_KEY = None`; `read_context` returns `{"result": {"threads": []}}` | `post("hi")` | `SwitchError` with detail `"no message id returned"` [7] |
| `test_post_thread_unsupported_raises` | `POST_THREAD_ARG = None` | `post("x", thread_id="r")` | `SwitchError` with detail `"threads unsupported"`; no `post_message` request [7] |
| `test_send_targeted_args` | result `{"event_id": "$t", "target_statuses": {"collector": "live"}}` | `send_targeted("collector", "Collect")` | body `{"target_names": ["collector"], "body": "Collect"}`; it returns the result [8] |
| `test_send_targeted_not_permitted_logs` | result `{"event_id": "$t", "target_statuses": {"collector": "not_permitted"}}`; caplog | `send_targeted("collector", "x")` | no exception; a WARNING contains `"not permitted"` [8] |
| `test_send_targeted_by_id_needs_map` | `TARGETED_TO_KIND = "id"`, no `agent_ids` | `send_targeted("reporter", "x")` | `SwitchError` with `"no Switch id for reporter"` [8] |
| `test_read_context_flattens_threads_oldest_first` | a result with two threads (root `r1` at t=5 with reply `x1` at t=9; root `r2` at t=7), a `room_join` entry `j` at t=1, and `truncated: True` | `read_context(5)` | the request body is `{"limit": 5}`; the result is `[{"message_id": "r1", "thread_id": None, "timestamp": 5, …}, {"message_id": "r2", "thread_id": None, …}, {"message_id": "x1", "thread_id": "r1", …}]` (sorted by timestamp, join dropped) [9] |
| `test_upsert_creates_then_updates` | create returns `{"result": {"document_id": "d-1"}}`; update returns `{"result": {}}` | `upsert_room_doc("close-board", "v1")`, then `upsert_room_doc("close-board", "v2")` | True, True; the create body is `{"name": "close-board", "content": "v1", "description": "Live close figures and open gaps.", "instructions": "Status board kept up to date by carbon-room. Read it; don't edit it."}`; the update body is `{"document_id": "d-1", "content": "v2"}` [10] |
| `test_upsert_finds_existing_doc_after_restart` | `connect_to_room` returns `documents: [{"id": "d-9", "name": "close-board", "description": "x"}]` | `upsert_room_doc("close-board", "v3")` | True; the only doc request is an update with `{"document_id": "d-9", "content": "v3"}`; no create [10] |
| `test_upsert_update_404_recreates` | known id `d-9` from connect; update returns 404; create returns `{"document_id": "d-10"}` | `upsert_room_doc(...)` | True; the requests are update, then create [10] |
| `test_upsert_exists_without_id_returns_false` | no documents from connect; create returns 409 `{"detail": "document already exists"}`; caplog | `upsert_room_doc(...)` | False; a WARNING [10] |
| `test_upsert_room_doc_unsupported_returns_false` | `DOCS_SUPPORTED = False` | `upsert_room_doc(...)` | False; 0 requests, including no `connect_to_room` [10] |
| `test_download_bytes` | GET returns 200 with content `b"%PDF-1.4"` | `download("mxc://switch.local/abc123", "/media/{server_name}/{media_id}?a={agent_id}&m={mxc}")` | `b"%PDF-1.4"`; URL `http://sw.test/media/switch.local/abc123?a=agent-cr&m=mxc%3A%2F%2Fswitch.local%2Fabc123`; Bearer header sent [11] |
| `test_download_error` | 404 | `download(...)` | `SwitchError` with `.op == "download"` and `.status == 404` [11] |
| `test_constants_match_switch_ops_json` | load `docs/switch-ops.json`, then `ops_ = data["operations"]` | for each `(op, arg)` in `[("post_message", POST_TEXT_ARG), ("post_message", POST_THREAD_ARG), ("send_targeted_message", TARGETED_TO_ARG), ("send_targeted_message", TARGETED_TEXT_ARG), ("read_context", READ_LIMIT_ARG), ("create_room_document", DOC_NAME_ARG), ("create_room_document", DOC_CONTENT_ARG), ("update_room_document", DOC_ID_ARG), ("connect_to_room", "room_id"), ("connect_to_room", "include_general_instructions")]` plus each key of `DOC_CREATE_EXTRA` for `create_room_document` | the op exists and `arg in ops_[op]["input_schema"]["properties"]`; `POST_ROOM_ARG is None` and `"room_id" not in ops_["post_message"]["input_schema"]["properties"]` [§0] |
| `test_key_never_logged` | `caplog.set_level(logging.DEBUG)`; one success, one 403, one network error | — | `"sk-test-secret"` is not in `caplog.text`, not in any `str(SwitchError)`, and not in `repr(client)` [13] |
| `test_aclose` | — | `await aclose()` | the underlying client `is_closed` [12] |

## 7. Fixtures and doubles
- `httpx.MockTransport` only. No `FakeSwitch`.
- `docs/switch-protocol-notes.md`, the body of `## S08 ops`, at most 25 lines:
  - the call shape and headers
  - the error mapping
  - the §0 table, and which values are schema-only
  - the `connect_to_room` step
  - the read_context shape
  - the doc upsert flow
  - the media path template (S2, still unknown)

## 8. Manual check (this is spikes S1, S5 and S6; do it right after merge)
With `make run` stopped, use carbon-room's and watchdog's ids and keys from `.env`:
1. **S1.** Open watchdog's socket (`filter=all`). Through carbon-room's `OpsClient` (with its own socket's
   connection id), `post("[spike] root")` and get back an id, then `post("[spike] reply", thread_id=<id>)`.
   In Mattermost the reply must be threaded.
2. **S5.** In watchdog's frames, the root's `payload.message_id` must equal the returned `event_id`. The reply's
   `payload.thread_id` must equal it too. If they differ, set `POST_ID_KEY = None`; the fallback uses
   `read_context` ids. Record which ids match in `docs/spikes.md`.
3. **S6.** `upsert_room_doc("close-board", "# test")`. Is it visible in Mattermost or in Switch Console? If
   neither, set `DOCS_SUPPORTED = False`.
4. **Eviction.** Check that `connect_to_room` didn't evict the socket: there should be no `evicted` frame, and
   `warning` is null.

A throwaway script that does steps 1–4 is at `scripts/spikes/m2_ops_check.py`. It posts two `[spike]` messages
and a targeted one, and creates then deletes a test document.

## 9. Done when
- [ ] Unit tests with a mocked transport check the headers, the body and the error mapping
- [ ] `test_constants_match_switch_ops_json` passes
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`
- [ ] §8 is done and recorded in `docs/spikes.md` (after merge; this doesn't block the PR)

## 10. Not in this spec
- Which agent posts what (SPEC-15 `SwitchRoom`).
- Registration and addressing (SPEC-09 and SPEC-09B), and room reset ops (SPEC-16B).

## 11. Open questions
None block execution. To settle live in §8:
1. Is `event_id` the same id that arrives as `message_id` and `thread_id` in frames (S5)? If not, gap threads
   can't be matched by `gap_for_thread` until `POST_ID_KEY` changes.
2. Does `connect_to_room` with the socket's connection id keep the socket alive? The docs say only one session
   per agent may act in a room. The header makes it the same session, but confirm.
