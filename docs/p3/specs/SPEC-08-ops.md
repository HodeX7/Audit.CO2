# SPEC-08 · Ops client
Stories: P3-2.3 · Branch: `p3-s08-ops` · PR title: "P3-S08 (2.3): ops client"
Depends on (must be merged): SPEC-06, and **M2 done** (`docs/switch-ops.json` and spikes S1, S5, S6 in
`docs/spikes.md`) · Wave: 2 · Estimated session time: 1.5 h

> **BLOCKED until §0 is filled in.** The Switch docs give no argument names for any op except
> `update_agent_detail` (checked 5 Nov 2026). M2 saves the real schemas to `docs/switch-ops.json`. Before this spec
> is handed to an executor, the user (or the M2 session) replaces every `TBD` in §0. **Executor: if any `TBD` is
> left, stop and report.**

> **Contract change (plan §3.11, edited in the same change as this spec)**
> 1. `ops.py` exports the §0 constants. SPEC-15's end-to-end test reads them to fake the server's responses.
> 2. `OpsClient.__init__` gains `agent_ids: Mapping[str, str] | None = None` (agent name → Switch id), used only
>    when `send_targeted_message` addresses agents by id.

## 0. M2 inputs (fill from `docs/switch-ops.json` and `docs/spikes.md`)

| Constant | What it is | Value |
|---|---|---|
| `POST_TEXT_ARG: str` | `post_message` argument holding the text | `TBD` |
| `POST_ROOM_ARG: str \| None` | `post_message` argument for the room id; None if the connection id binds the room | `TBD` |
| `POST_THREAD_ARG: str \| None` | `post_message` argument for the thread root id; None if spike S1 failed | `TBD` |
| `POST_ID_KEY: str \| None` | key of the new message id in `post_message`'s result; None if spike S5 failed | `TBD` |
| `TARGETED_TO_ARG: str` | `send_targeted_message` argument naming the target(s) | `TBD` |
| `TARGETED_TO_KIND: str` | one of `"name"`, `"id"`, `"names"`, `"ids"` (the last two are lists) | `TBD` |
| `TARGETED_TEXT_ARG: str` | `send_targeted_message` argument holding the text | `TBD` |
| `READ_LIMIT_ARG: str` | `read_context` argument for how many messages | `TBD` |
| `READ_MESSAGES_KEY: str \| None` | key of the message list in `read_context`'s result; None if the result is the list | `TBD` |
| `READ_NEWEST_FIRST: bool` | True if `read_context` lists the newest message first | `TBD` |
| `CONTEXT_ID_KEY`, `CONTEXT_BODY_KEY`, `CONTEXT_SENDER_KEY`, `CONTEXT_THREAD_KEY: str` | keys inside each message `read_context` returns | `TBD` |
| `DOCS_SUPPORTED: bool` | spike S6: True if a room document is visible to people somewhere useful | `TBD` |
| `DOC_NAME_ARG`, `DOC_CONTENT_ARG: str` | `create_room_document` and `update_room_document` arguments | `TBD` |
| `DOC_UPDATE_BY: str` | `"name"` if `update_room_document` takes the name, `"id"` if it takes a document id | `TBD` |
| `DOC_ID_ARG: str \| None`, `DOC_ID_KEY: str \| None` | only when `DOC_UPDATE_BY == "id"`: update's id argument and the id key in create's result | `TBD` |

Op names are fixed: `POST_MESSAGE = "post_message"`, `SEND_TARGETED = "send_targeted_message"`,
`READ_CONTEXT = "read_context"`, `CREATE_DOC = "create_room_document"` and `UPDATE_DOC = "update_room_document"`.
If M2 finds a different name for any of them, change that constant here too.

## 1. Goal
An async `httpx` client for Switch ops, one per agent. It calls any op with the right headers and unwraps the
result. It maps HTTP errors to one `SwitchError` with the server's detail. It offers the four helpers the room
needs: post, targeted message, read context, and upsert a room document. It also downloads attachment bytes.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.5 (Ops, Media), §2 and §3.11
- `docs/switch-ops.json`, and the S1, S2, S5 and S6 sections of `docs/spikes.md`
- `carbon_room/room/settings.py` (SPEC-06)

## 3. Files
- Create `carbon_room/room/ops.py`
- Create `tests/room/test_ops.py`
- Modify `docs/switch-protocol-notes.md`: replace only the body of `## S08 ops`

## 4. Public interface
```python
# the §0 constants and the five op names, at module level

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
    async def post(self, text: str, thread_id: str | None = None) -> str
    async def send_targeted(self, to_agent: str, text: str) -> Any
    async def read_context(self, limit: int = 20) -> list[dict]
    async def upsert_room_doc(self, name: str, content: str) -> bool
    async def download(self, mxc: str, path_template: str) -> bytes
    async def aclose(self) -> None
    def __repr__(self) -> str      # never contains api_key
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
   result is cached after the first success, so a second call makes no request.
5. **`post(text, thread_id=None)`.**
   - The args are `{POST_TEXT_ARG: text}`, plus `{POST_ROOM_ARG: room_id}` when both are set.
   - With `thread_id`: if `POST_THREAD_ARG is None`, raise `SwitchError(None, "post_message", "threads
     unsupported")` without calling. Otherwise add `{POST_THREAD_ARG: thread_id}`.
   - The id is `result[POST_ID_KEY]` when `POST_ID_KEY` is set and `result` is a dict holding a non-empty str or
     int (ints become str).
   - Otherwise, fall back: `msgs = await read_context(10)`, and take the `message_id` of the **last** message
     (oldest-first order) whose `body == text`.
   - If there is still no id, raise `SwitchError(None, "post_message", "no message id returned")`.
6. **`send_targeted(to_agent, text)`.**
   - The target value depends on `TARGETED_TO_KIND`:
     - `name`: `to_agent`
     - `id`: `agent_ids[to_agent]`
     - `names`: `[to_agent]`
     - `ids`: `[agent_ids[to_agent]]`

     A missing `agent_ids` entry raises `SwitchError(None, "send_targeted_message", f"no Switch id for
     {to_agent}")`.
   - The args are `{TARGETED_TO_ARG: value, TARGETED_TEXT_ARG: text}`.
   - When `"not_permitted"` appears anywhere in `json.dumps(result)`, log a WARNING `send_targeted to <agent> was
     not permitted`. It doesn't raise. The result is returned.
7. **`read_context(limit=20)`.**
   - Calls `READ_CONTEXT` with `{READ_LIMIT_ARG: limit}`. The list is `result[READ_MESSAGES_KEY]`, or `result`
     itself when the key is None.
   - Each entry is normalised to `{"message_id", "body", "sender", "thread_id"}` using the `CONTEXT_*` keys.
     Missing keys become `""`, or None for `thread_id`.
   - The result is returned oldest first: reversed when `READ_NEWEST_FIRST` is True.
8. **`upsert_room_doc(name, content)`.**
   - If `DOCS_SUPPORTED` is False, return False with no call.
   - **By name:**
     1. Call `UPDATE_DOC` with `{DOC_NAME_ARG: name, DOC_CONTENT_ARG: content}`.
     2. On a `SwitchError` whose status is 404, or whose detail contains `not found` (case-insensitive), call
        `CREATE_DOC` with the same args.
     3. If create fails with status 409, or with a detail containing `exist` (case-insensitive), call
        `UPDATE_DOC` once more.
     4. Return True.
   - **By id:**
     1. Keep a per-client `name → id` cache.
     2. With no cached id, call `CREATE_DOC` and cache `result[DOC_ID_KEY]`. If it fails as "exists", log a
        WARNING and return False.
     3. With a cached id, call `UPDATE_DOC` with `{DOC_ID_ARG: id, DOC_CONTENT_ARG: content}`.
     4. Return True.
   - Any other `SwitchError` propagates.
9. **`download(mxc, path_template)`.**
   - The template's fields are `{agent_id}`, `{mxc}` (`urllib.parse.quote(mxc, safe="")`), `{server_name}` (the
     mxc host) and `{media_id}` (the last path segment of the mxc). `str.format` fills them.
   - Sends `GET` to the result with the auth header and returns `response.content`.
   - A status of 400 or above raises `SwitchError(status, "download", detail)`.
10. **`aclose()`** closes the httpx client.
11. **Secrets.** No log line, exception or `repr()` contains the API key or the `Authorization` header.
    `__repr__` is `f"OpsClient(agent_id={agent_id!r})"`.

## 6. Test plan
Every test uses `httpx.MockTransport(handler)`, where `handler` records each `httpx.Request` and returns the
response the test sets up. Build the client with `OpsClient("http://sw.test", "agent-cr", "sk-test-secret",
connection_id="conn-1", room_id="room-1", transport=mock, agent_ids={"collector": "agent-col"})`. Each test is an
`async def` run with `asyncio.run`. Expected bodies are built from the `ops` constants. For the fallback and
unsupported cases, `monkeypatch.setattr(ops, "POST_ID_KEY", None)` and the like.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_call_headers_and_unwrapped_body` | 200 `{"result": {"ok": 1}}` | `call("whoami", {"a": 1})` | method POST; URL `http://sw.test/agents/agent-cr/ops/whoami`; headers `authorization == "Bearer sk-test-secret"`, `content-type == "application/json"`, `x-switch-connection-id == "conn-1"`; `json.loads(body) == {"a": 1}` [2] |
| `test_call_without_connection_id_omits_header` | `client.connection_id = None` | `call("x")` | no `x-switch-connection-id` header; body `{}` [2] |
| `test_result_unwrapped` | 200 `{"result": [1, 2]}`; then 200 `{"nope": 1}` | `call("x")` twice | `[1, 2]`; then `SwitchError` with detail `"response has no result"` [2] |
| `test_error_mapping_400_403_404_409` (parametrized) | status `s` with `{"detail": "bad thing"}` for 400, 403, 404 and 409; then 500 with text body `"x" * 400` | `call("op1")` | `SwitchError` with `.status == s`, `.op == "op1"`, `.detail == "bad thing"`, `str(e) == f"op1 failed ({s}): bad thing"`; for 500, `len(.detail) == 300` [3] |
| `test_error_detail_non_string` | 400 `{"detail": [{"loc": ["x"]}]}` | `call("op1")` | `.detail == json.dumps([{"loc": ["x"]}])` [3] |
| `test_network_error_maps_to_switch_error` | handler raises `httpx.ConnectError("refused")` | `call("op1")` | `SwitchError` with status None and `"refused"` in detail [3] |
| `test_list_ops_cached` | 200 `{"operations": {"post_message": {"description": "d", "input_schema": {}}}}` | `list_ops()` twice | the same dict; 1 request, `GET /agents/agent-cr/ops` [4] |
| `test_post_top_level_and_thread_args` | 200 `{"result": {POST_ID_KEY: "m-1"}}` (skip if `POST_THREAD_ARG is None`) | `post("hi")`; `post("re", thread_id="root-1")` | first body `{POST_TEXT_ARG: "hi"}` plus `{POST_ROOM_ARG: "room-1"}` when set; second adds `{POST_THREAD_ARG: "root-1"}` [5] |
| `test_post_returns_message_id` | result `{POST_ID_KEY: 42}` (skip if `POST_ID_KEY is None`) | `post("hi")` | `"42"` [5] |
| `test_post_message_id_fallback_read_context` | `POST_ID_KEY = None`; `post_message` returns `{"result": {}}`; `read_context` returns 3 messages with bodies `["hi", "other", "hi"]` and ids `["a", "b", "c"]` in oldest-first order (built with the `CONTEXT_*` keys, reversed if `READ_NEWEST_FIRST`) | `post("hi")` | `"c"`; the second request is to `read_context` with `{READ_LIMIT_ARG: 10}` [5, 7] |
| `test_post_no_id_raises` | `POST_ID_KEY = None`; `read_context` returns `[]` | `post("hi")` | `SwitchError` with detail `"no message id returned"` [5] |
| `test_post_thread_unsupported_raises` | `POST_THREAD_ARG = None` | `post("x", thread_id="r")` | `SwitchError` with detail `"threads unsupported"`; 0 requests [5] |
| `test_send_targeted_args` | 200 `{"result": {}}` | `send_targeted("collector", "Collect")` | body `{TARGETED_TO_ARG: <value per TARGETED_TO_KIND for "collector" / "agent-col">, TARGETED_TEXT_ARG: "Collect"}` [6] |
| `test_send_targeted_not_permitted_logs` | result `{"results": {"collector": "not_permitted"}}`; caplog | `send_targeted("collector", "x")` | no exception; a WARNING contains `"not permitted"` [6] |
| `test_send_targeted_unknown_id` | `TARGETED_TO_KIND = "id"` | `send_targeted("reporter", "x")` | `SwitchError` with `"no Switch id for reporter"` [6] |
| `test_read_context_normalised_oldest_first` | a result with 2 messages (shape per §0) | `read_context(5)` | `[{"message_id": "a", "body": "one", "sender": "s", "thread_id": None}, {"message_id": "b", …}]`, oldest first [7] |
| `test_upsert_room_doc_create_then_update` | `DOC_UPDATE_BY = "name"`; first `update` returns 404, `create` returns 200, a later `update` returns 200 | `upsert_room_doc("close-board", "x")` twice | True both times; ops called in order `[update, create, update]` [8] |
| `test_upsert_exists_then_update` | `DOC_UPDATE_BY = "name"`; update 404, create 409, update 200 | `upsert_room_doc(...)` | True; ops `[update, create, update]` [8] |
| `test_upsert_by_id_caches_id` | `DOC_UPDATE_BY = "id"`, `DOC_ID_KEY = "id"`, `DOC_ID_ARG = "document_id"`; create returns `{"result": {"id": "d-1"}}` | upsert twice | ops `[create, update]`; the update body has `{"document_id": "d-1", DOC_CONTENT_ARG: "x"}` [8] |
| `test_upsert_room_doc_unsupported_returns_false` | `DOCS_SUPPORTED = False` | `upsert_room_doc(...)` | False; 0 requests [8] |
| `test_download_bytes` | GET returns 200 with content `b"%PDF-1.4"` | `download("mxc://switch.local/abc123", "/media/{server_name}/{media_id}?a={agent_id}&m={mxc}")` | `b"%PDF-1.4"`; URL `http://sw.test/media/switch.local/abc123?a=agent-cr&m=mxc%3A%2F%2Fswitch.local%2Fabc123`; Bearer header sent [9] |
| `test_download_error` | 404 | `download(...)` | `SwitchError` with `.op == "download"` and `.status == 404` [9] |
| `test_constants_match_switch_ops_json` | load `docs/switch-ops.json`, then `ops_ = data.get("operations", data)` | for each `(op, arg)` in `[(POST_MESSAGE, POST_TEXT_ARG), (POST_MESSAGE, POST_ROOM_ARG), (POST_MESSAGE, POST_THREAD_ARG), (SEND_TARGETED, TARGETED_TO_ARG), (SEND_TARGETED, TARGETED_TEXT_ARG), (READ_CONTEXT, READ_LIMIT_ARG), (CREATE_DOC, DOC_NAME_ARG), (CREATE_DOC, DOC_CONTENT_ARG)]` with `arg` not None | `op in ops_` and `arg in ops_[op]["input_schema"].get("properties", {})` [§0] |
| `test_key_never_logged` | `caplog.set_level(logging.DEBUG)`; one success, one 403, one network error | — | `"sk-test-secret"` is not in `caplog.text`, not in any `str(SwitchError)`, and not in `repr(client)` [11] |
| `test_aclose` | — | `await aclose()` | the underlying client `is_closed` [10] |

## 7. Fixtures and doubles
- `httpx.MockTransport` only. No `FakeSwitch`.
- `docs/switch-protocol-notes.md`, the body of `## S08 ops`, at most 25 lines:
  - the call shape and headers
  - error mapping
  - the §0 table as it was filled in
  - the S1 and S5 fallbacks
  - how room documents behave (S6)
  - the media path template (S2)

## 8. Manual check
After merge, against the real server, with carbon-room's id and key from `.env`:
`.venv/bin/python -c "import asyncio; from carbon_room.room.ops import OpsClient; …"`. Post `hello` and get back
an id. Post `reply` with that id as `thread_id`; it must appear threaded in Mattermost.

## 9. Done when
- [ ] Unit tests with a mocked transport check the headers, the body and the error mapping
- [ ] §0 has no `TBD`, and `test_constants_match_switch_ops_json` passes
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Which agent posts what (SPEC-15 `SwitchRoom`).
- Registration and addressing (SPEC-09), and room reset ops (SPEC-16B).

## 11. Open questions
1. **Blocking:** every `TBD` in §0.
2. If `update_room_document` needs an id that only `create` returns, a restart loses the cached id. `upsert` then
   returns False with a WARNING, and the board stops updating. This is acceptable, since the board is first in
   the cut order. A `list_room_documents` op, if M2 finds one, would fix it.
