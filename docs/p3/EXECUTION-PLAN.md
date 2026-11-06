# P3 Execution Plan — Switch room, demo and submission

> **For agentic workers.** This plan is the parent of every P3 spec. Spec-writing sessions read all of it.
> Execution sessions read §0.3, §2, §3 and their own spec only. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship everything P3 owns in Carbon Room: the Switch room client, router, orchestrator, room messages,
reproducible setup, README, demo video and submission. Work test-first, one spec per PR.

**Architecture:** Four Switch agents (`carbon-room`, `collector`, `watchdog`, `reporter`) run in one Python
process. Each holds a WebSocket and answers pings straight from its read loop. Domain events go onto one asyncio
queue. A dispatcher decodes them, deduplicates them, and classifies them into intents. Handlers in
`carbon_room/agents/` call `carbon_room.core` on a thread pool and post replies through a `Room` port. The ledger,
owned by P1 and P2, is the only state that matters. The room layer formats values and never computes them.

**Tech stack:**
- Python 3.11+ (the local venv is 3.12).
- `websockets` 17 (the `websockets.asyncio` API), `httpx` 0.28 (`MockTransport` in tests) and `langgraph` 1.2
  (`StateGraph`, `MemorySaver`).
- `pyyaml`, `python-dotenv`, `pytest` 9 and `ruff`.
- No pytest-asyncio. Async tests call `asyncio.run(...)` inside plain test functions.

**Source documents:**
- `00-CONTRACTS.md`: shared contracts. P3 owns §8 and `people.yaml`.
- `P3-switch-room-and-demo.md`: P3 stories, with their "Done when" boxes.
- `Carbon Room Architecture.html`: the team-lead view.
- `docs/HANDOFF.md` and `contracts/CHANGES.md`: P1's guarantees and the asks it makes of P3.
- Switch docs at https://docs.switchagents.ai, mainly the `/switch-rooms/internals/agent-protocol.md`,
  `agent-connection.md` and `agent-events.md` pages. These were read 5 Nov 2026 and summarised in §1.5.

---

## 0. How to use this plan

### 0.1 The pipeline

```
this plan ──► Opus session (no context) ──► docs/p3/specs/SPEC-NN-<slug>.md ──► you review
          ──► Sonnet session per spec (no context) ──► tests first (red) ──► code (green) ──► PR ──► merge
```

- **Spec writer (Opus).** Turns one or more plan entries in §5 into self-contained specs. It writes no
  implementation code. It may pin exact strings, fixture contents and test assertions.
- **Executor (Sonnet).** Gets one spec. It writes the tests and interface stubs first, commits them red, then
  implements without touching the tests, and opens one PR.
- **You.** Review each spec before execution and each PR before merge. You run the manual tracks in §6.

### 0.2 Branches, worktrees and PRs

- **Do PR-0 first.** Commit the planning documents to `main`: `00-CONTRACTS.md`,
  `P3-switch-room-and-demo.md`, `Carbon Room Architecture.html`, `docs/P3-CHECKLIST.md` and this plan. Fresh
  sessions and worktrees only see committed files.
- **Commit specs to `main` per wave.** Use a small PR titled `docs(p3): specs for wave N`. Execution sessions run
  in separate worktrees and need the spec file to exist there.
- **Run one worktree per parallel executor**, so sessions never fight over the checkout:
  ```bash
  git fetch origin && git worktree add ../audit-s02 -b p3-s02-grammar origin/main
  cd ../audit-s02 && python3 -m venv .venv && .venv/bin/pip install -q -e . pytest ruff
  ```
  Each worktree needs its own `.venv`. The editable install points at the checkout it was made in.
- **Branch name:** `p3-sNN-<slug>`.
- **PR title:** `P3-SNN (<story ids>): <title>`, for example `P3-S02 (3.1): grammar parser`.
- **PR body:**
  - the five-line plan required by contracts §11
  - the spec's "Done when" boxes, ticked
  - the tail of the pytest and ruff output
  - a **Deviations** section: "none", or what changed and why
- **Merge order** follows the dependency graph in §4. Rebase a branch onto `main` after each dependency merges.
- **Shared files rule.** Only the spec named as owner edits each of these:
  - `Makefile`: S16
  - `README.md`: S17
  - `config/people.yaml`: S03
  - `.env.example`: S06
  - `tests/room/conftest.py`: S01
  - `docs/switch-protocol-notes.md`: each spec edits only the section headed with its own id

  Later specs put their fixtures inside their own test modules. Tick `docs/P3-CHECKLIST.md` on `main` after each
  merge, not inside feature PRs.

### 0.3 The test-first protocol (executors follow this exactly)

1. **Branch.** `git switch -c <branch>` from up-to-date `origin/main`, or work in the worktree made for the spec.
2. **Red commit.**
   - Write every test in the spec's test plan. Add **interface stubs only**: the exact signatures from the
     spec's "Public interface", with bodies that `raise NotImplementedError`. Constants and dataclasses may be
     complete.
   - Run `.venv/bin/pytest -q`. Every new test must fail with `NotImplementedError` or an assertion, never an
     `ImportError` or a syntax error. Every pre-existing test must still pass.
   - Commit: `test(p3-sNN): failing tests for <title>`.
3. **Green commit.**
   - Implement until everything passes. **Do not edit any file under `tests/` in this step.**
   - If a test looks wrong, stop and report which test and why. The spec is the authority, and the fix is a
     spec change approved by the user.
   - Commit: `feat(p3-sNN): <title>`.
4. **Checks.**
   - `.venv/bin/pytest -q` must pass in full.
   - `.venv/bin/ruff check carbon_room/room carbon_room/agents tests/room tests/fakes <other files you touched>`
     must pass. The whole repo fails ruff on `main` because of P1's code, which is not your concern.
   - `git diff --stat origin/main` lists only the files in the spec.
5. **PR.** `git push -u origin HEAD`, then open it with `gh pr create`, using the title and body from §0.2.

Strict mode, optional: one Sonnet session does steps 1–2 only. A second, fresh session does steps 3–5, given
only the spec and the red branch. This guarantees the tests were written without sight of any implementation.

### 0.4 Prompt for the spec-writing session (Opus)

```
You are writing implementation specs for P3 of the Carbon Room repository. You have no other context; the repo
has everything. Read docs/p3/EXECUTION-PLAN.md in full first. Then, for each spec I name, read the contract
sections, P3 stories and source files listed under "Read" in that spec's plan entry. For Switch-related specs,
also read docs/switch-protocol-notes.md, docs/spikes.md and docs/switch-ops.json if they exist.

Write docs/p3/specs/SPEC-NN-<slug>.md for: <SPEC IDs>. Use the template in §0.5 of the plan.
- No implementation code. You may pin exact strings, fixture file contents, and test names with
  arrange/act/assert, including short assertion snippets.
- The plan's §3 interfaces bind every spec. If one must change, put a "Contract change" box at the top of the
  spec and edit §3 of the plan in the same change.
- Check the plan's claims against the code. Run small snippets with .venv/bin/python if useful. Record any
  disagreement under "Open questions" instead of guessing.
- Every behaviour rule maps to at least one test. Every test has concrete inputs and exact expected outputs.
- Keep each spec executable by a fresh session in about 1–2 hours. If one is bigger, propose a split.
When done, list the files you wrote and any open questions that block execution.
```

### 0.5 Spec template

```markdown
# SPEC-NN · <title>
Stories: P3-x.y, … · Branch: p3-sNN-<slug> · PR title: "P3-SNN (x.y, …): <title>"
Depends on (must be merged): SPEC-…, or none · Wave: N · Estimated session time: N h

## 1. Goal
Two or three sentences.

## 2. Read before starting
Exact file paths and contract sections. Nothing else is needed.

## 3. Files
Create / Modify / Test, an exhaustive list. Nothing outside it changes.

## 4. Public interface
Exact signatures, dataclasses, constants and exceptions, with types. Tests are written against this and only this.

## 5. Behaviour
Numbered rules. Each says what happens for an input, including errors and edge cases.

## 6. Test plan
A table: test name | arrange | act | assert, with exact values and strings. Rule numbers in brackets.

## 7. Fixtures and doubles
Which fakes from tests/fakes are used, and the exact contents of any new fixture file.

## 8. Manual check (if any)
What to try in the real room after merge, and what you should see.

## 9. Done when
- [ ] story "Done when" items (copied)
- [ ] every test in §6 passes; full `pytest -q` passes
- [ ] ruff passes on the touched paths
- [ ] no literal site id, YYYY-MM month, or CL-/G-/S-<digits> id under carbon_room/

## 10. Not in this spec
## 11. Open questions
Anything unresolved. The executor stops if one of these blocks a test.
```

### 0.6 Definition of done (every spec)

This combines contracts §11 with P3's own rules:
- The red commit precedes the green commit, and no test file changes in the green commit.
- `pytest -q` passes in full, and ruff passes on the touched paths.
- The spec's "Done when" boxes are ticked in the PR.
- Nothing listed in §2 is violated.

---

## 1. Project context (for readers with zero context)

### 1.1 What Carbon Room is

A Switch chat room (Mattermost) where a team closes a month of emissions:

- Agents collect bills and build a shared SQLite ledger, then calculate.
- A rules-based Watchdog posts each missing, conflicting or stale item as a thread with a named owner.
- People fix those items by replying in the thread. Only VERIFIED rows count, and a person publishes.
- Every human action carries the Switch `chat_message_id`. Without the room there is no close.

That is why Switch counts for 30% of the score. README plus reproducibility counts for 45%.

**Demo story** (contracts §10, about 90 seconds):
1. The Lead types `@carbon-room close October`.
2. `@carbon-room` posts the plan and hands work to `@collector`.
3. `@collector` claims "All 5 October sources collected." This is the false "done".
4. `@watchdog` opens four gap threads:
   - Warehouse-2's "October" bill is really a September bill. Owner: Priya.
   - HQ diesel has two invoices 400 L apart (`pick A` / `pick B`).
   - The data-centre invoice uses last year's Ember factor.
   - HQ electricity is 38% above September.
5. `@carbon-room` refuses a clean total, then shows the verified and excluded figures and coverage.
6. People reply in the threads. Priya uploads the real bill and the Lead picks and approves. The total moves.
7. `@reporter draft`, then `@carbon-room publish` (Lead only), then `@reporter trace S-001`.

### 1.2 Who owns what

| Person | Owns |
|---|---|
| P1 (Ujjwal) | Ingestion, ledger, audit chain, `core.py` facade: `start_close`, `ingest`, `ingest_file`, `verify_audit`, `resume_state`, `latest_close`, `gap_for_thread`, `record_gap_thread`, `budget_usage`, `explain` |
| P2 (Richa) | `calculate`, `check`, `resolve`, `summary`, `draft_report`, `publish`, `trace`, plus `config/carbon_room.yaml` and `config/factors.csv` |
| **P3 (you)** | Everything under `carbon_room/room/`; the P3 agent modules in `carbon_room/agents/` (not its `__init__.py`); `config/people.yaml`; the Makefile and README; the setup docs, spikes, demo, video and submission |


**Demo cast (decided 5 Nov):** akshar = Lead (person id `lead`), richa = Warehouse-2 site manager (id `priya`, replaces "Priya"), ujjwal = Finance (id `finance`, read-only in the demo). Keep the ids; `people.yaml` sets `username` and `name`. The room is `emissions-reporting`, created through Switch's `create_room` (channels made directly in Mattermost are not bridged). `post_message` takes `body` and `thread_id`; see `docs/switch-ops.json` for the other argument names (S08 must use those).

### 1.3 State of `main` at commit 4a8e3ca (Thu 5 Nov, 19:00 PT)

**Works (P1):**
- `models.py` holds all §2 types.
- The P1 functions in `core.py` work.
- `config/sites.yaml` and the seed data under `data/seed/2026-09` and `data/seed/2026-10` are present, plus
  `data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf`.
- 41 tests pass.
- A smoke run (`start_close` → `ingest` → `verify_audit` → `explain`) works when
  `config/carbon_room.yaml` exists. It produced 9 claims, the statement "All 5 2026-10 sources collected.", and
  `explain` answered "UNKNOWN for warehouse-2, because no VERIFIED ledger rows match, owned by priya".

**Missing (P2):**
- `calculate`, `check`, `resolve`, `summary`, `draft_report`, `publish` and `trace` raise `NotImplementedError`.
- `config/carbon_room.yaml` is absent, so `start_close` raises `ValueError`.
- P2's branch `feat/calc-check` is the legacy `carbonroom` package with no merge base. It has to be ported.

**P1 defects to chase.** These are not P3 work, but they break the demo:
1. `collect.ingest` stamps baseline (September) claims with the close month (`claim_month = close["month"]`).
2. Diesel claims get `scope "2"`. Diesel is Scope 1.
3. `ruff check .` fails on `main` with 183 errors.
4. The replay cache path `data/cache/` is gitignored. Contract §9 sets `llm.mode: replay`, and that mode raises
   `FileNotFoundError` on a cache miss. Fix it one of two ways:
   - commit `data/cache/extractions/`, or
   - have P2 ship `mode: rules`, the P1 offline default, for the demo.
5. `data/seed/EXPECTED.md` does not exist.
6. `.env.example` names `claude-sonnet-4-5`; contract §9 says `claude-sonnet-5-5`.

**P3:** nothing exists except the placeholder `carbon_room/room/__init__.py`.

**Machine:**
- Docker Desktop 29.9 (arm64) is running, and Switch Console is installed.
- `uv` is not installed. Use `python3 -m venv .venv`. The repo already has a `.venv` with every dependency.

### 1.4 Questions to raise with P2 (record answers in `docs/p3/specs/` open questions)

1. `core.resolve(gap_id, …)` has no `close_id`, and P1 restarts gap ids at `G-1` for each close. P2's resolve
   must use the latest close. P3 always passes the gap id it got from `gap_for_thread` or from the latest close.
2. Contract §10 says Warehouse-2's MISSING (R1) and false-done (R4) findings "share one thread". P1 enforces one
   thread root per gap. So either P2 emits one gap for both, or the room posts two roots. **P3 assumes one gap**
   (the fake models it as R4 PERIOD with option `upload`).
3. R6 DATACENTRE has no options. Does it become a gap? **P3 handles both cases:** a gap with no options is posted
   as informational. The fake returns the R6 finding but opens no gap for it.
4. What are the dict shapes of `Report.gaps` and `Report.conflicts`? P3 renders `gap_id` and `title` if present.
5. Which files does `publish` write to `out/<month>/v<n>/`? The video ends on `coverage.html`.
6. Who writes `tests/test_publish_needs_room.py`? The README cites it. P3 proposes to write it (S17).

### 1.5 Switch facts (from the docs; spikes confirm the starred items)

**Base URL and health**
- The base URL is the server address Switch Console shows. A local server picks free ports; there is no fixed
  port. If an address answers with a web page, it is the Gateway, not the server.
- `GET /health` is public. 200 means the URL is right; 401 means right host, wrong path.

**Auth and registration**
- Every call sends `Authorization: Bearer <agent api key>`.
- The registration key works only for `POST /agents`, and agent keys never work there.
- `POST /agents` request body:
  `{name, description, connector_type, display_name?, integration_profile: {connection_model, message_exchange,
  pre_invocation_mediation: [], post_invocation_mediation: [], event_reporting: []}}`.
  The name matches `^[a-z0-9][a-z0-9._-]*$`.
- The response is `{id, api_key}`, and the key is shown once. A name that is already taken returns 409.
- Console-created agents get `.switch/agents/<name>.json` =
  `{"env": {"SWITCH_API_ENDPOINT", "SWITCH_API_TOKEN", "SWITCH_AGENT_ID"}}`.

**Addressing**
- `POST /agents/{id}/ops/update_agent_detail {"agent_id", "addressing": "anyone"}`.★ It may be refused. The
  fallback is to set "Anyone" in Console.
- `@name`, `@name,` and `@name:` address an agent, case-insensitively. A mention inside backticks counts.
- Follow-ups: a thread reply reaches the agent that last spoke in that thread.

**WebSocket**
- `GET /agents/{id}/connection/ws?connection_id=<uuid>&rooms=<id>&filter=all|addressed&start_from=<seq>&expected_generation=<g>`.
- Optional parameters: `client` and `client_version`.
- Close codes: 4401 bad auth (no frame); 4400 bad query; 4403 room not served; 4409 taken over or conflict;
  1012 server restart, so reconnect.

**Domain frames**
- Envelope: `{"event": "message", "data": {"type", "room_id", "bridge_id", "channel_type", "payload",
  "sequence"}, "id": <same as sequence>}`.
- `message` payload: `addressed`, `sender`, `sender_name`, `message_id`, `body`, `timestamp` (ms), `thread_id`
  (nullable), `attachments[]`. Each attachment has `filename`, `mimetype`, `size`, `mxc` and `msgtype`.
- `command` payload: `command`, `args`, `user_id`, `user_name`, `thread_id`.
- `room_join` payload: `member`, `member_name`, `timestamp`, `listening`.
- Sender ids look like `@switch-user-…:<server>`. Treat them as opaque.

**Control frames**
- `connection_state`: always first. Fields `generation`, `cursor`, `rooms`, `heartbeat_interval_seconds`, …
- Also `ping`, `evicted` (`code`, `reason`), `gap` (`resumed_at`, …), `refused` (`status`, `detail`),
  `subscription_changed` and `room_released`.
- ★ Envelope unknown. Parse both `{"type": …}` and `{"event": …, "data": {…}}`.

**Heartbeat and resume**
- The server pings every 2 s. Reply `{"type":"pong","cursor":<highest sequence>}` **before** processing events.
- 6 s of silence ends in `evicted` `heartbeat_lapsed`.
- Eviction codes:
  - `taken_over`: final; never reconnect.
  - `closed`: don't auto-retry.
  - `heartbeat_lapsed`, `no_stream`, `unfenced`, `connection_error`: reconnect.
- Resume with the same `connection_id`, `start_from=<cursor>` and `expected_generation`. On a `gap` frame, set
  the cursor to `resumed_at`.

**Ops**
- Discovery: `GET /agents/{id}/ops` returns `{"operations": {name: {"description", "input_schema"}}}`.
- Call: `POST /agents/{id}/ops/{op}`. The body is the unwrapped args object; the response is `{"result": …}`.
  The `X-Switch-Connection-Id` header binds the call to a room.
- Errors: 400 bad args, 403 denied, 404 unknown op, 409 dead connection id.
- ★ `post_message`: the thread argument's name and the returned message id are undocumented (spikes S1, S5).
- `send_targeted_message` reports `not_permitted` per target.
- ★ `create_room_document` fails if the name exists; an agent can update only its own documents.
- `archive_room` and `create_room` exist. ★ The `invite_agent_to_room` schema is unknown.

**Media and reactions**
- ★ Media download routes are undocumented (spike S2). Attachments are pointers (`mxc`), not bytes.
- Reactions are absent from the event catalogue, so never treat an emoji as an approval (contracts §8).

---

## 2. Global constraints (every spec includes these implicitly)

**Dependency boundary**
- P3 code never imports `carbon_room.ledger` or anything under it. It calls `carbon_room.core` only; async code
  goes through `AsyncCore` (§3.4).
- Reading `carbon_room.config` (sites, config, people) and `carbon_room.models` is allowed.

**What the room layer may not do**
- It never computes an emissions number, a coverage figure or a status. Templates format values that `core`
  returned.
- It never blocks the asyncio loop. Core, LLM and file work go through the thread pool, and pings are answered
  in the socket read loop.

**Literals and output**
- No literal site id (`hq`, `warehouse-2`, `dc-eu-west`) appears anywhere under `carbon_room/`. Neither does a
  `\d{4}-\d{2}` month or a `CL-`/`G-`/`S-` followed by digits. This includes docstrings and example strings;
  `tests/test_no_literals.py` scans for them. Tests, `config/` and `data/` may contain them.
- No `print` outside CLI entry points (`register`, `doctor`, `reset`). Use `logging.getLogger(__name__)`.
- Never log or print an API key, registration key or `Authorization` header.

**Contract and state**
- Don't change any signature or type in `00-CONTRACTS.md` §2–§7. P3 may change §8 and `people.yaml` (it owns
  them) through a proposal file (`docs/proposals/NNN-*.md`) in its own small PR.
- Every human-triggered core call passes `actor` (built from the authenticated Switch sender) and
  `chat_message_id = event.message_id`. Never take a role, user id or message id from message text.
- Quantities are `Decimal`. Display tCO2e to one decimal place, `ROUND_HALF_UP`.
- Paths are relative to the repo root (the process working directory): `data/inbox/`, `out/`, `var/`.

**Tests**
- Test files live in `tests/room/` and test doubles in `tests/fakes/`. The test directories have no
  `__init__.py`, so every test module basename must be unique across `tests/`.
- Import doubles as `from fakes.fake_core import FakeCore`. This works because pytest puts `tests/` on `sys.path`.
- Async tests use `asyncio.run(...)`, wrap waits in `asyncio.wait_for(..., timeout)`, and keep any single test
  under 5 s. The whole `tests/room` suite stays under 20 s.

---

## 3. P3 internal contract (binding across specs)

This is P3's own interface layer. Specs refine the wording, but names, signatures and meanings here are fixed.

### 3.1 Module map and data flow

```
Switch server ──ws──► room/connection.py AgentConnection ×4 (answers ping inline; on_event = dispatcher.submit)
                                    │ (agent_name, frame)
                                    ▼
              room/dispatch.py Dispatcher ── decode (room/events.py) ── room/frames.py helpers
                   │  drop: non-message, other room, own agents, already-handled message_id
                   │  classify (room/app.py: grammar + acceptance rule) → Intent; "ignore" is dropped
                   │  lanes: mutating intents → one FIFO worker; reads → concurrent tasks
                   ▼
              room/app.py handle(ctx, event, intent) → actor = identity.actor_for(...) → HANDLERS[kind]
                   ▼
   agents/orchestrator.py · gaps.py · resolution.py · publish.py · reports.py · ask.py · notices.py
                   │ await ctx.core.<fn>(...)        → room/async_core.py → ThreadPoolExecutor → carbon_room.core
                   │ await ctx.room.post(agent, …)   → room/noise.py NoiseGuard → room/switch_room.py SwitchRoom
                   ▼                                                                │
              room/messages.py (pure templates)                                    ▼
                                                     room/ops.py OpsClient ×4 ──http──► Switch ops
```

| File | Spec | One responsibility |
|---|---|---|
| `carbon_room/room/frames.py` | S01 | Classify raw frames (kind, fields, sequence), whatever their envelope |
| `carbon_room/room/ports.py` | S01 | `AGENT_NAMES`, the `Room` protocol, `Context` |
| `carbon_room/room/async_core.py` | S01 | `AsyncCore`: §4 core functions as awaitables on a thread pool |
| `tests/fakes/fake_core.py`, `tests/fakes/fake_room.py`, `tests/room/conftest.py` | S01 | Test doubles and shared fixtures |
| `carbon_room/room/grammar.py` | S02 | Text → `Intent`; reply normalisation |
| `carbon_room/room/identity.py`, `config/people.yaml` | S03 | Switch sender → `Actor`; display names |
| `carbon_room/room/errors.py` | S04 | Exception → reply text |
| `carbon_room/room/messages.py` | S05 | Every room message as a pure function |
| `carbon_room/room/settings.py`, `carbon_room/room/events.py` | S06 | Env → `Settings`; frame → `RoomEvent` |
| `carbon_room/room/connection.py`, `tests/fakes/fake_switch.py` | S07 | WebSocket lifecycle; fake server |
| `carbon_room/room/ops.py` | S08 | HTTP ops client |
| `carbon_room/room/register.py` | S09 | Agent registration CLI |
| `carbon_room/room/dispatch.py` | S10 | Queue, dedupe, lanes, error capture |
| `carbon_room/room/router.py`, `carbon_room/room/attachments.py` | S11 | Gap reply → option; attachment → managed file |
| `carbon_room/agents/gaps.py`, `carbon_room/agents/orchestrator.py` | S12 | Close flow (LangGraph) and gap roots |
| `carbon_room/agents/resolution.py`, `publish.py`, `reports.py`, `ask.py` | S13 | Human-driven handlers |
| `carbon_room/agents/notices.py`, `hooks.py`, `room/noise.py`, `room/board.py`, resume in `orchestrator.py` | S14 | Room hygiene |
| `carbon_room/room/app.py`, `switch_room.py`, `run.py` | S15 | Wiring and runner |
| `carbon_room/room/doctor.py`, `reset.py`, `scripts/reset_demo.sh`, `Makefile` | S16 | Reproducibility |
| `README.md`, `docs/setup-switch.md`, `tests/test_publish_needs_room.py` | S17 | Documentation |

### 3.2 `room/frames.py` (S01)

```python
DOMAIN_KINDS = frozenset({"message", "command", "room_join"})
CONTROL_KINDS = frozenset({"connection_state", "gap", "evicted", "subscription_changed",
                           "room_released", "ping", "refused"})
def frame_kind(frame: dict) -> str | None
def frame_fields(frame: dict) -> dict
def sequence_of(frame: dict) -> int | None
def pong(cursor: int) -> str
```

- `frame_kind` returns `frame["data"]["type"]` first when it is a domain kind. The docs don't say whether a
  `command` frame's `event` is `"message"`; SPEC-01 records this change. Otherwise it checks `frame["event"]`,
  then `frame["type"]`, then a control kind in `frame["data"]["type"]`, and returns the first value in
  `DOMAIN_KINDS | CONTROL_KINDS`. Otherwise it returns None.
- `frame_fields` returns `frame["data"]` when it is a dict. Otherwise it returns the frame itself without
  `event`/`type`.
- `sequence_of` returns `frame["id"]`, else `frame["data"]["sequence"]`, else None. It returns an int or None.
- `pong` returns `json.dumps({"type": "pong", "cursor": cursor})`.

### 3.3 `room/ports.py` (S01)

```python
AGENT_NAMES: tuple[str, ...] = ("carbon-room", "collector", "watchdog", "reporter")
AGENT_TITLES: dict[str, str] = {"carbon-room": "Carbon Room", "collector": "Collector",
                                "watchdog": "Watchdog", "reporter": "Reporter"}

class Room(Protocol):
    async def post(self, agent: str, text: str, *, thread_id: str | None = None,
                   essential: bool = True) -> str: ...      # returns the new message id ("" if buffered)
    async def send_targeted(self, from_agent: str, to_agent: str, text: str) -> None: ...
    async def upsert_doc(self, agent: str, name: str, content: str) -> bool: ...   # False = unsupported
    def link(self, message_id: str) -> str: ...
    def begin_close(self, close_id: str) -> None: ...

async def noop_phase_end(close_id: str) -> None

@dataclass
class Context:
    core: Any                                    # AsyncCore (or AsyncCore(FakeCore()) in tests)
    room: Room
    display: Callable[[str], str] = str          # person id → "@username" / name (identity.display)
    today: Callable[[], date] = <UTC today>
    on_phase_end: Callable[[str], Awaitable[None]] = noop_phase_end
    threads: bool = True                         # spike S1 result
    attachments_mode: str = "inbox"              # "download" | "inbox" (spike S2)
    inbox_dir: Path = Path("data/inbox")
    download: Callable[[Any], Awaitable[bytes]] | None = None
    out_dir: Path = Path("out")
    state: dict = field(default_factory=dict)    # per-process memory, e.g. budget notices already sent
```

- A thread post (`thread_id` set) never counts as top-level.
- `essential=False` marks posts the noise guard may merge: "total moved" lines and budget notices.
- Every handler has the signature
  `async def handler(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None`.

### 3.4 `room/async_core.py` (S01)

```python
CORE_FUNCTIONS: tuple[str, ...] = ("start_close", "ingest", "ingest_file", "calculate", "check", "resolve",
    "summary", "draft_report", "publish", "trace", "verify_audit", "resume_state", "latest_close",
    "gap_for_thread", "record_gap_thread", "budget_usage", "explain")
class AsyncCore:
    def __init__(self, core: Any, executor: concurrent.futures.Executor | None = None) -> None
    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]
```

- `AsyncCore` raises `AttributeError` for names outside `CORE_FUNCTIONS`.
- Each call runs `getattr(core, name)(*args, **kwargs)` through `loop.run_in_executor`. With no executor it
  creates a `ThreadPoolExecutor(max_workers=4, thread_name_prefix="core")`.
- Core exceptions propagate unchanged.

### 3.5 `room/events.py` (S06)

```python
@dataclass(frozen=True)
class Attachment:
    filename: str; mimetype: str | None; size: int | None; mxc: str | None; msgtype: str | None

@dataclass(frozen=True)
class RoomEvent:
    type: str                     # "message" | "room_join"
    room_id: str; message_id: str; thread_id: str | None
    sender: str; sender_name: str; body: str
    attachments: tuple[Attachment, ...]; addressed: bool; timestamp: int
    receiving_agent: str; sequence: int
    @property
    def in_thread(self) -> bool    # thread_id is not None and thread_id != message_id

def decode(frame: dict, receiving_agent: str,
           own_sender_ids: frozenset[str] = frozenset()) -> RoomEvent | None
```

`decode` returns None in these cases:
- the frame is a control frame or a `command` (Switch handles bang commands)
- the frame is malformed
- the message has no `message_id`
- the sender is one of our agents: `sender in own_sender_ids`, or `sender_name.strip().lower()` is in
  `AGENT_NAMES`

For `room_join` it sets `message_id=f"join:{sequence}"` and `body=""`.

### 3.6 `room/grammar.py` (S02)

```python
@dataclass(frozen=True)
class Intent:
    kind: str; args: dict; target_agent: str | None
def parse(body: str, *, in_thread: bool, today: date) -> Intent
def normalize_reply(text: str) -> tuple[str, str]        # (key, rest)
```

This deliberately differs from story 3.1's `parse(body, receiving_agent, in_thread)`. Targeting comes from the
explicit mention, and acceptance per socket is decided in `app.classify` (§3.13). Mention-less messages are
never commands.

| kind | args | target_agent | Produced by |
|---|---|---|---|
| `close.start` | `{"month": "YYYY-MM"}` | `carbon-room` | `@carbon-room close <Month> [<YYYY>]` or `close <YYYY-MM>` |
| `close.status` | `{}` | `carbon-room` | `@carbon-room status` |
| `close.resume` | `{}` | `carbon-room` | `@carbon-room resume` |
| `close.publish` | `{}` | `carbon-room` | `@carbon-room publish` |
| `report.draft` | `{}` | `reporter` | `@reporter draft` |
| `report.trace` | `{"tag": "S-NNN"}` | `reporter` | `@reporter trace S-14` (normalised to three digits) |
| `audit.verify` | `{}` | `reporter` | `@reporter verify audit` |
| `help` | `{"reason": str \| None}` | mentioned agent | `@<agent> help`; a bare `@<agent>`; a known command with bad args |
| `ask` | `{"question": str}` | mentioned agent | any other text addressed to one of our agents |
| `gap.reply` | `{"text": str}` | `watchdog` | in a thread with no mention; or a mention whose remaining text is a reply key |
| `gap.fallback` | `{"gap_id": "G-n", "text": str}` | `watchdog` | `G-n <reply>` at the start (after an optional mention), anywhere |
| `ignore` | `{}` | None | everything else (chatter, other people's mentions) |

**Precedence:**
1. `gap.fallback`.
2. A mention of one of our agents:
   - a command owned by that agent; else
   - when `in_thread` and the remaining text normalises to a reply key, `gap.reply`; else
   - `help` if the remaining text is empty, `ask` otherwise.
3. No mention:
   - `in_thread` → `gap.reply`
   - otherwise → `ignore`

**Commands are bound to their agent.** `@reporter publish` is an `ask`.

**Default year.** The current year, unless the month is later than today's month, in which case the previous
year. For example, `close December` on 2026-11-05 gives `2025-12`.

**Month names.** Full names and three-letter abbreviations in any case, plus `sept`.

**Mention syntax.** Matching ignores case, extra spaces, a trailing `,` or `:` after the mention, and backticks
around it.

**`normalize_reply`.**
- Lowercase the key and keep `rest` with its original case.
- Collapse whitespace and strip trailing `.!`.
- `pick <x>` and `pick option <x>` → `("pick <x>", "")`.
- `approve`, `approved` → `("approve", "")`.
- `reject`, `rejected`, plus an optional `:`/`—`/`-` and a reason → `("reject", reason)`.
- `upload [name]` → `("upload", name)`.
- Anything else → `(normalised text, "")`.

### 3.7 `room/identity.py` and `config/people.yaml` (S03)

```python
def actor_for(sender_id: str, sender_name: str, *,
              agent_ids: Mapping[str, str] | None = None) -> Actor
def person(person_id: str) -> dict | None
def display(person_id: str) -> str
def is_known(sender_id: str) -> bool
def placeholders() -> list[str]
```

**`actor_for`**
- Known person: `Actor("human", person.id, person.name, person.role)`.
- `sender_id` in `agent_ids` (a Switch id → agent name map): `Actor("agent", name, AGENT_TITLES[name], None)`.
- Anyone else is a guest: `Actor("human", f"guest:{sender_id}", sender_name or sender_id, None)`.

**`display`** returns `"@" + username` when the person has a non-empty `username`, else their name, else the id
itself.

**`placeholders`** returns problems for `make doctor`:
- ids containing `<`
- `lead` or `priya` with an empty `switch_ids`

People come from `carbon_room.config.load_people()["people"]`. `people.yaml` adds an optional `username` field.
P3 owns that file, and the change is noted in a §9 proposal.

### 3.8 `room/errors.py` (S04)

```python
@dataclass(frozen=True)
class ErrorReply:
    text: str; error_id: str | None
def reply_for(exc: BaseException, *, agent: str | None = None,
              owner_name: str | None = None) -> ErrorReply
```

| Exception | Reply text |
|---|---|
| `NotAllowed` | "Only the Lead or the gap owner ({owner_name}) can do that." when `owner_name` is given, else "Only the Lead can do that." |
| `LockHeld` | "@collector is still reading that source. Try again in a moment." |
| `BudgetExceeded` | "@{agent} has hit its budget for this close and has stopped. The Lead can raise it in config." (`agent` defaults to `carbon-room`) |
| `NotFound` | "I can't find that: {exc}." |
| `NotImplementedError` | "That step isn't built yet ({exc}). The ledger is unchanged." |
| `ValueError` | "I couldn't do that: {exc}." |
| `NeedsRoomEvent` | Generic text below; logged at ERROR as a bug |
| anything else | "Something went wrong on my side (error {error_id}). The ledger is unchanged." |

The generic `error_id` is 8 lowercase hex characters, and the traceback is logged at ERROR. The other rows have
`error_id=None`.

### 3.9 `room/messages.py` (S05): formatting rules and starting copy

**Helpers (pure)**
- `t(kg: Decimal | None) -> str`: kg ÷ 1000, quantised to 0.1 `ROUND_HALF_UP`, with thousands separators, then
  " tCO2e". `Decimal("22900")` → `"22.9 tCO2e"`; `Decimal("1234567")` → `"1,234.6 tCO2e"`; None → `"n/a"`.
- `t_value(tco2e: Decimal) -> str`: the same rounding and format for a figure already in tonnes.
- `pct(p: Decimal) -> str`: quantised to 0 decimals, then "%". `Decimal("61")` → `"61%"`.
- `month_label(month: str) -> str`: `"2026-10"` → `"October 2026"`.
- `month_of(close_id: str) -> str`: `"2026-10-v1"` → `"2026-10"`, via `rsplit("-v", 1)`.

**Templates.** Each takes values and display strings and returns `str`. None of them reads config or calls core.

| Function | Starting copy (S05 pins the final text) |
|---|---|
| `close_plan(month_label, close_id, site_names, factor_set)` | `Starting the {month} close ({close_id}).`<br>`Sites: {names}. Factor set {fs} is locked.`<br>`Plan: @collector gathers the sources, I calculate, @watchdog checks every row. Anything that fails a check becomes a thread with an owner.` |
| `handoff_collect(month_label, site_names)` | `Collect {month} for {names}.` |
| `handoff_check(month_label)` | `Check {month}: every rule, every claim.` |
| `collector_statement(report)` | `report.statement` verbatim, plus `\nCould not read {n} file(s).` when `failed_sources` is non-empty |
| `gap_root(gap, finding, owner_display, *, fallback_hint=False)` | `**{gap_id} · {kind}** {title}` / `Owner: {owner}` / `Evidence:` with one `> {line}` per `finding.evidence` (the section is omitted when `finding` is None) / `Reply in this thread with:` then one `` - `{key}`: {label} `` per option. A `reject` option renders as `` `reject <reason>` ``. With no options: `No reply needed. {owner} follows this up.` With `fallback_hint`: `` Or type `{gap_id} {first key}` anywhere in the room. `` |
| `options_help(gap)` | `` I didn't catch that. Reply with one of: `pick A`, `pick B`. `` (the keys come from the gap) |
| `already_resolved(gap)` | `{gap_id} is already resolved.` |
| `old_close_gap(gap)` | `{gap_id} belongs to an earlier close ({close_id}). Reply in the thread from the current close.` (added by SPEC-05; used by SPEC-13) |
| `checking()` | `Checking…` |
| `outcome_resolved(gap)` / `outcome_open(gap, reason)` | `Resolved. {gap_id} is closed and the ledger is updated.` / `{gap_id} is still open: {reason}` |
| `summary_post(month_label, summary, display)` | With open gaps: `I can't give a clean {month} total yet.` / `Verified: {t} · Excluded (not verified): {t} · Coverage: {pct}` / `Sources: {sv} of {se} expected sources verified.` / `Open gaps ({n}): G-1 @priya · G-2 @lead …`, plus the DC line when `dc_line` is set. With no gaps: `{month} is ready to draft.` / the same two figure lines / `Next: @reporter draft` |
| `dc_line(dc)` | `Data centre: location-based {t} · market-based {t} ({rec_flag}) · AI line UNVERIFIED: {note}` |
| `total_moved(before, after)` | `Total moved {t} → {t}, coverage {pct} → {pct}.` |
| `draft(report, month_label)` | `Draft v{version} for {month}` / headline figures / `Open and excluded:` gap lines or `none` / `Conflicts:` / DC line / `Compliance:` flags / `Factor versions:` / `{n} source tags. Ask @reporter trace {first tag} to see one.` / `The Lead publishes with @carbon-room publish.` |
| `published(report, approver_display, paths)` | `Published v{version} by {approver}.` / `Verified {t} · Coverage {pct} · {source_coverage}` / `Files: {paths}` |
| `trace_card(tag, link)` | `{tag} · {activity} · {status}` / `File: {file}, page {page}` / `Excerpt: "{excerpt}"` / `SHA-256: {sha[:12]}…` / `Factor: {factor_id} ({version}, {geography})` / `Recompute: {recompute}` / `Result: {t(kgco2e)}` / `Approved by: {approver or "Tier 1 (automatic)"}` + ` · {link}` when the tag has a chat message id |
| `audit_result(check)` | `Audit chain intact: {events} events.` / `Audit chain broken at event {first_bad_event_id} ({events} events checked).` |
| `resume_line(month_label, phase, gaps, display, link)` | `Resuming the {month} close at {phase}.` / `Open gaps: G-1 @priya ({link}) · …` or `No open gaps.` |
| `budget_warn(agent, warn_label)` / `budget_stopped(agent)` | `@{agent} has used {warn_label} of its budget for this close.` (`warn_label` is formatted from config `budgets.warn_at`, e.g. "80%") / the `BudgetExceeded` text from §3.8 |
| `board(month_label, summary, display, link)` | Markdown: a header line, the figure lines, then a table `\| Gap \| Owner \| Status \| Thread \|` |
| `no_close()` | `` No close has started yet. Start one with `@carbon-room close <Month>`. `` |
| `gap_not_found(gap_id)` / `tag_not_found(tag)` / `no_reply_needed()` | `I can't find an open {gap_id} in this close.` / `I can't find {tag} in this close.` / `No reply needed here.` |
| `help_text(reason=None)` | The optional reason line, then the §8 command list |

### 3.10 `room/settings.py` (S06): environment variables

| Variable | Meaning | Default |
|---|---|---|
| `SWITCH_SERVER` | Server base URL from Switch Console (not the Gateway) | required |
| `SWITCH_ROOM_ID` | The `emissions-reporting` room id | required to run |
| `SWITCH_REGISTRATION_KEY` | Gateway "API Keys" registration key | only for `register` |
| `SWITCH_AGENT_<NAME>_ID`, `SWITCH_AGENT_<NAME>_KEY` | Per agent; `<NAME>` is the upper-snake agent name (`CARBON_ROOM`, `COLLECTOR`, `WATCHDOG`, `REPORTER`) | written by `register` |
| `CARBON_ROOM_THREADS` | `1` if spike S1 passed | `1` |
| `CARBON_ROOM_ATTACHMENTS` | `download` if spike S2 passed, else `inbox` | `inbox` |
| `CARBON_ROOM_SINGLE_AGENT` | `1` if spike S4 failed (one socket with `[Watchdog]` prefixes) | `0` |
| `MATTERMOST_PERMALINK_BASE` | Prefix for message links (spike S5) | unset → links render as `message <id>` |
| `SWITCH_MEDIA_PATH` | Media download path template with `{agent_id}` and `{mxc}` (spike S2) | unset |

```python
@dataclass(frozen=True)
class AgentCreds:
    name: str; agent_id: str; api_key: str

@dataclass(frozen=True)
class Settings:
    server: str; room_id: str; agents: dict[str, AgentCreds]; threads: bool; attachments_mode: str
    single_agent: bool; permalink_base: str | None; media_path: str | None
    inbox_dir: Path = Path("data/inbox")

def env_name(agent: str, field: Literal["ID", "KEY"]) -> str     # "carbon-room","ID" → "SWITCH_AGENT_CARBON_ROOM_ID"
def load_settings(env: Mapping[str, str] | None = None) -> Settings
def missing(env: Mapping[str, str] | None = None, *, for_run: bool = True) -> list[str]
```

- `load_settings` reads `.env` with python-dotenv when `env` is None. It raises `ValueError` naming every
  missing variable.
- `missing` returns the missing variable names.

### 3.11 `room/ops.py` (S08)

```python
class SwitchError(Exception):
    status: int | None; op: str; detail: str
class OpsClient:
    def __init__(self, server: str, agent_id: str, api_key: str, *, connection_id: str | None = None,
                 room_id: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 10.0) -> None
    connection_id: str | None                  # settable after the socket opens
    async def list_ops(self) -> dict[str, dict]
    async def call(self, op: str, args: dict | None = None) -> Any
    async def post(self, text: str, thread_id: str | None = None) -> str
    async def send_targeted(self, to_agent: str, text: str) -> Any
    async def read_context(self, limit: int = 20) -> list[dict]
    async def upsert_room_doc(self, name: str, content: str) -> bool
    async def download(self, mxc: str, path_template: str) -> bytes
    async def aclose(self) -> None
```

S08 is written after spike M2, so the exact argument names come from `docs/switch-ops.json`. SPEC-08 adds two
things:
- Module constants for those names (`POST_TEXT_ARG`, `POST_THREAD_ARG`, `POST_ID_KEY` and others), which
  SPEC-15's loop test reads.
- An `agent_ids: Mapping[str, str] | None = None` keyword on `__init__`.

### 3.12 `room/connection.py` (S07)

```python
class AuthError(Exception): ...
def backoff_delays() -> Iterator[float]          # 1, 2, 4, 8, 16, 30, 30, …
class AgentConnection:
    def __init__(self, agent_name: str, agent_id: str, api_key: str, server: str, room_ids: list[str],
                 filter: Literal["all", "addressed"], on_event: Callable[[str, dict], None], *,
                 connection_id: str | None = None, client_version: str = "0.1.0",
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None
    connection_id: str; cursor: int | None; generation: int | None
    connected: asyncio.Event                     # set after each connection_state
    async def run(self) -> None                  # returns after stop() or a final error
    async def stop(self) -> None
```

### 3.13 `room/dispatch.py` (S10) and the acceptance rule (S15)

```python
MUTATING_KINDS = frozenset({"close.start", "close.resume", "close.publish", "report.draft",
                            "gap.reply", "gap.fallback"})
class Dispatcher:
    def __init__(self, *, decode: Callable[[str, dict], RoomEvent | None],
                 classify: Callable[[RoomEvent], Intent],
                 handle: Callable[[RoomEvent, Intent], Awaitable[None]],
                 on_error: Callable[[RoomEvent, Intent, BaseException], Awaitable[None]],
                 room_id: str, max_reads: int = 4, seen_limit: int = 5000) -> None
    def submit(self, agent_name: str, frame: dict) -> None   # sync and non-blocking; this is on_event
    async def run(self) -> None
    async def join(self) -> None                             # waits until queued and in-flight work is done
    async def stop(self) -> None
```

**Pipeline for each frame:**
1. Decode. Drop the frame if it is None or `type != "message"`.
2. Drop it if the room is not ours.
3. Drop it if its `message_id` was already **handled**.
4. Classify. `ignore` is dropped **without** marking the id handled, so the same message arriving on the
   addressed agent's socket is still accepted.
5. Mark the id handled.
6. Route it: mutating kinds go to one FIFO worker; other kinds run as concurrent tasks, capped at `max_reads`.
7. If the handler raises, call `on_error`. A failure inside `on_error` is logged.

**The acceptance rule** lives in `app.classify` (S15):
- `gap.reply` and `gap.fallback` are accepted if `event.addressed` or `identity.is_known(event.sender)`.
- Every other non-ignore kind is accepted only if `single_agent`, or
  `event.addressed and intent.target_agent == event.receiving_agent`.
- Anything else becomes `Intent("ignore", {}, None)`.

### 3.14 `room/router.py` and `room/attachments.py` (S11)

```python
@dataclass(frozen=True)
class GapAction:
    gap: Gap; option: Option; payload: dict; filename: str | None
@dataclass(frozen=True)
class NoMatch:
    gap: Gap; reason: Literal["unknown_reply", "gap_resolved", "no_options"]
def match_reply(gap: Gap, text: str, has_attachment: bool) -> GapAction | NoMatch
def find_gap(gaps: list[Gap], gap_id: str) -> Gap | None

MAX_BYTES = 10 * 1024 * 1024
class AttachmentMissing(Exception):
    text: str
def safe_name(name: str) -> str
async def fetch(*, message_id: str, attachment: Attachment | None, typed_name: str | None, mode: str,
                inbox_dir: Path, download: Callable[[Attachment], Awaitable[bytes]] | None) -> Path
```

### 3.15 Handler table (S12–S15)

| Intent | Handler | Posts as | Where |
|---|---|---|---|
| `close.start` | `orchestrator.handle_close_start` | carbon-room → collector → watchdog → carbon-room | top level |
| `close.status` | `reports.handle_status` | carbon-room | thread of the command |
| `close.resume` | `orchestrator.handle_resume` | carbon-room | top level |
| `close.publish` | `publish.handle_publish` | carbon-room | top level; refusals in the command's thread |
| `report.draft` | `publish.handle_draft` | reporter | top level |
| `report.trace` | `reports.handle_trace` | reporter | thread of the command |
| `audit.verify` | `reports.handle_verify_audit` | reporter | thread of the command |
| `help` | `reports.handle_help` | target agent | thread of the command |
| `ask` | `ask.handle_ask` | target agent | thread of the question |
| `gap.reply`, `gap.fallback` | `resolution.handle_gap_reply` | watchdog; carbon-room for "total moved" | gap thread; "total moved" at top level, non-essential |

"Thread of the command" means `thread_id = event.thread_id or event.message_id`.

### 3.16 Fake scenario (`tests/fakes/fake_core.py`, S01)

This mirrors contracts §10 so room tests tell the real story. **The numbers are fake.** They must never appear
in the README or demo script; those quote `data/seed/EXPECTED.md` only. The fake computes summaries from line
flags, so resolutions can happen in any order.

**Close and gaps**
- Close: month `2026-10`, sites `hq`, `warehouse-2` and `dc-eu-west`, factor set `FS-2026-10`.
- The first `start_close` returns `2026-10-v1`; a repeat for the same month returns `-v2`.
- `ingest` returns `IngestReport(close_id, 9, [CL-0001…CL-0009], [], "All 5 October sources collected.")`.

| Gap | Rule · kind | Owner | Claims | Options (`key` → action, params, label) | Title | Evidence |
|---|---|---|---|---|---|---|
| G-1 | R4 · PERIOD | priya | CL-0005 | `upload` → upload `{site: warehouse-2, month: 2026-10, activity: electricity_kwh}` "Upload the October bill" | Warehouse-2 October bill is a September bill | `File name: warehouse2_electricity_2026-10.pdf`; `Billing period: 1–30 Sep 2026` |
| G-2 | R2 · CONFLICTING | lead | CL-0003, CL-0002 | `pick A` → pick `{claim_id: CL-0003}` "Invoice 4471 — 2,000 L"; `pick B` → pick `{claim_id: CL-0002}` "Invoice 4471-rev — 2,400 L" | HQ October diesel has two invoices 400 L apart | `Invoice 4471: Diesel delivered: 2000 L`; `Invoice 4471-rev: Diesel delivered: 2400 L` |
| G-3 | R3 · STALE | lead | CL-0001 | `approve` → approve `{use_factor_id: EMBER-2025-IE}` "Use the locked Ember 2025 IE factor"; `reject` → reject "Exclude the cloud line" | Data centre invoice uses last year's Ember factor | `vendor_factor_ref: Ember 2024 IE`; `Locked factor set FS-2026-10 uses Ember 2025` |
| G-4 | R5 · VARIANCE | lead | CL-0004 | `approve` → approve "Accept +38% against September"; `reject` → reject "Exclude HQ electricity" | HQ October electricity is 38% above September | `September: 35000 kWh`; `October: 48300 kWh (+38%)` |

`check()` also returns an R6 DATACENTRE finding with no options and `blocking=False`, but opens **no** gap for it.

**Lines (kgCO2e)**
- `hq-elec` 9660 (G-4)
- `diesel-A` 5320 and `diesel-B` 6384 (G-2)
- `wh2-sep` 3500 (G-1)
- `dc` 4320 (G-3)

| After | verified | excluded | coverage | sources verified (of 4) |
|---|---|---|---|---|
| `check` | 0 | 29184 | 0 | 0 |
| G-1 `upload` (adds CL-0010 `wh2-oct` 3600 verified; drops `wh2-sep`) | 3600 | 25684 | 12 | 1 |
| G-2 `pick A` (drops `diesel-B`) | 8920 | 13980 | 39 | 2 |
| G-3 `approve` | 13240 | 9660 | 58 | 3 |
| G-4 `approve` | 22900 | 0 | 100 | 4 |

A `reject` resolves the gap and the line stays excluded.

**Rules the fake enforces**
- **Roles.**
  - A human `actor` with an empty `chat_message_id` raises `NeedsRoomEvent` in `start_close`, `resolve` and
    `publish`.
  - `resolve` by a guest (`role` None) raises `NotAllowed`. So does an actor who is neither the lead nor the gap
    owner.
  - `publish` by a non-lead raises `NotAllowed`.
- **Errors.**
  - `upload` without `payload["path"]` raises `ValueError`.
  - Resolving a resolved gap raises `ValueError(f"gap {gap_id} is already resolved")`.
  - An unknown gap raises `NotFound`.
- **Threads.** `record_gap_thread` raises `ValueError` if the message id is already linked to another gap, and
  does nothing if the gap already has a root. `gap_for_thread` returns None for an unknown thread.
- **Phases.**
  - `start_close` → OPEN; `ingest` → COLLECTING; `calculate` → CALCULATING.
  - `check` → AWAITING_HUMANS, or CHECKING when no gaps are open.
  - `resolve` → AWAITING_HUMANS, or CHECKING when none are left.
  - `draft_report` → DRAFTED; `publish` → PUBLISHED.
- **Summary.** `summary` returns a `CloseSummary` with:
  - the table's numbers as `Decimal`
  - `sources_expected=4`
  - open gaps sorted by gap number
  - `dc_line = DcLine(Decimal("4320"), Decimal("0"), Decimal("1.2"), "Market-based 0 relies on certificates;
    certificate quality not verified", "UNVERIFIED", "No per-model AI breakdown on the invoice.")`
- **Report.** `draft_report` returns a `Report`:
  - `version` 1; tCO2e = kg ÷ 1000
  - `source_coverage` `"{sv} of 4 expected sources verified"`
  - `gaps`: one `{"gap_id", "title", "owner"}` per open gap
  - `conflicts`: G-2 if it is still open
  - `factor_versions` `["DEFRA 2026", "EGRID 2024", "EMBER 2025"]`
  - `s_tags`: one `SourceTag` per verified line, `S-001` upward in line order
  - `compliance_flags` `["Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero"]`
  - `approver` None and `published_at` None

  `publish` sets `approver = actor.id` and `published_at = "2026-11-06T17:00:00Z"`, and writes no files.
- **Trace.** `trace(close_id, tag)` returns the matching `SourceTag`, or raises `NotFound(f"unknown tag: {tag}")`.
- **Explain.** The answer depends on which site the question names (an id or a `sites.yaml` name):
  - no verified line for that site:
    `"UNKNOWN for warehouse-2, because no VERIFIED ledger rows match, owned by priya"`
  - after G-1: `"Verified ledger facts: CL-0010: warehouse-2 18000 kWh, 3600 kgCO2e, status VERIFIED"`

  These match P1's real phrasing.
- **Audit, budget and resume.**
  - `verify_audit` returns `AuditCheck(True, len(self.calls), None)`.
  - `budget_usage` returns `self.budget` (default `{}`, settable by tests).
  - `resume_state` returns `(phase, open gaps)`, and `latest_close` returns the newest close id.
- **Test hooks.**
  - `self.calls: list[tuple[str, dict]]` records every call with its bound arguments.
  - `self.delay: float = 0` makes every method `time.sleep(delay)` first.
  - `self.fail: dict[str, BaseException]` makes the named method raise once.
  - `self.on_resolve_open: list[Finding]` lets a test make `resolve` open new gaps.
  - `self.keep_open: set[str]` names gaps that `resolve` leaves OPEN with no effect (added by SPEC-01).
  - `self.audit: AuditCheck | None` overrides `verify_audit` (added by SPEC-01).
  - `FakeRoom.link` returns `"message m-3"` (SPEC-01).

---

## 4. Order of work

### 4.1 Waves and dependency graph

```
Wave 0 (alone, first)   S01 foundation ─────────────────────────────────────────────┐
Wave 1 (parallel)       S02 grammar · S03 identity · S04 errors · S05 messages       │   M1 Switch setup (you)
                        S06 settings+events · S07 connection+fake switch       M2 spikes (you + interactive session)
                        S09 register (starts once S06 merges; M2 can use curl until then)
Wave 2 (parallel)       S08 ops (needs M2) · S10 dispatcher (S02,S06) · S11 router+attachments (S02,S06)
                        S16 Makefile/doctor/reset (S06,S03; reset's room part needs S08)
Wave 3                  S12 close flow (S01,S05) ──► S13 resolution/publish/reports/ask (S04,S11,S12)
                                                └──► S14 hygiene: resume, notices, noise, board (S12)
Wave 4                  S15 app wiring + runner + e2e (everything above) ──► M3 people.yaml real ids
Wave 5                  S17 README & docs · S18 real-core integration (when P2 lands) · M4–M8 demo, video, submit
```

**Critical path:** S01 → S05 → S12 → S13 → S15 → M5 rehearsal → M7 video. A second path runs S01 → S06 → S07
and M2 → S08 → S15.

### 4.2 Time budget (session hours; waves run in parallel worktrees)

| Spec | h | Spec | h | Spec | h |
|---|---|---|---|---|---|
| S01 | 1.5 | S07 | 2 | S13 | 2 |
| S02 | 1 | S08 | 1.5 | S14 | 1.5 |
| S03 | 0.5 | S09 | 1 | S15 | 2 |
| S04 | 0.5 | S10 | 1 | S16 | 1.5 |
| S05 | 1.5 | S11 | 1 | S17 | 1 |
| S06 | 1 | S12 | 2 | S18 | 2 |

With three or four parallel executors, waves 0–4 fit in about 10–12 wall-clock hours. The deadlines:
- Fri 6 Nov 12:00 PT: README complete and reproducible (S16, S17, M6).
- Fri 6 Nov 17:00 PT: freeze (video recorded).
- Sat 7 Nov 10:00 PT: submit.

**Cut order if late:** S14's board (→ none), then S14's notices, then S09's invite step (→ do it by hand in
Console), then S18's polish.

### 4.3 Recommended spec-writing batches

- **Opus session A:** S01–S07 and S09.
- **Opus session B, after M2:** S08 and S10–S16.
- **Opus session C:** S17, and S18 once P2's core has landed.

Review and merge each batch's specs to `main` (PR "docs(p3): specs for …") before starting executors.

---

## 5. Specs

Each entry has the decisions the spec writer must carry into the spec. "Tests" lists the minimum test set by
name; the spec adds exact values.

### S01 · Foundation: ports, AsyncCore, frames, fakes
**Stories:** 8.1 (fake core), plus scaffolding · **Wave:** 0 · **Depends on:** none
**Read:** contracts §2, §4, §10; `carbon_room/core.py`; `carbon_room/models.py`; `tests/test_core_signatures.py`;
`tests/test_no_literals.py`; `tests/conftest.py`; plan §3.2–§3.4 and §3.16.
**Files:**
- Create: `carbon_room/room/frames.py`, `carbon_room/room/ports.py`, `carbon_room/room/async_core.py`
- Create: `tests/fakes/fake_core.py`, `tests/fakes/fake_room.py`
- Create: `tests/room/conftest.py`, `tests/room/test_fake_core.py`, `tests/room/test_foundation.py`,
  `tests/room/test_boundaries.py`
- Create: `tests/room/fixtures/people.yaml`
- Create: `docs/switch-protocol-notes.md` and `docs/spikes.md` as skeletons with one heading per owning spec
  (`## S06 events`, `## S07 connection`, `## S08 ops`, `## S09 register`) and one per spike S1–S6.

**Produces:**
- §3.2, §3.3 and §3.4 exactly.
- `FakeCore`, with the §3.16 behaviour and test hooks.
- `FakeRoom` (below).
- Fixtures in `tests/room/conftest.py`:
  - `people_config` points `CARBON_ROOM_CONFIG_DIR` at a tmp dir holding the repo's `sites.yaml`, the fixture
    `people.yaml` and a minimal `carbon_room.yaml` (`default_factor_set`, `factor_sets`, `budgets.warn_at: 0.8`,
    `noise.max_top_level_posts: 12`). It calls `config.clear_caches()` before and after.
  - `fake_core` returns a `FakeCore()`.
  - `fake_room` returns a `FakeRoom()`.
  - `ctx` returns `Context(core=AsyncCore(fake_core), room=fake_room, display=lambda pid: f"@{pid}",
    today=lambda: date(2026, 11, 5))`.

**FakeRoom (tests/fakes/fake_room.py)**

```python
@dataclass
class Post:
    agent: str; text: str; thread_id: str | None; essential: bool; message_id: str
class FakeRoom:
    posts: list[Post]; targeted: list[tuple[str, str, str]]; docs: dict[str, str]
    supports_docs: bool = True; closes: list[str]
    async def post(...) -> str          # ids "m-1", "m-2", … in order
    async def send_targeted(...) -> None
    async def upsert_doc(...) -> bool    # stores and returns True unless supports_docs is False
    def link(self, message_id) -> str    # "(message m-3)"
    def begin_close(self, close_id) -> None
    def top_level(self) -> list[Post]
    def in_thread(self, thread_id) -> list[Post]
```

The fixture `people.yaml` holds:
- lead: switch id `@switch-user-lead:test`, username `lead`, role lead
- priya: switch id `@switch-user-priya:test`, username `priya`, role site_manager, sites `[warehouse-2]`
- finance: role finance
- auditor: role auditor

**Tests:**
- `test_fake_core_signatures_match_core`: for every name in `CORE_FUNCTIONS`, the parameter names (minus
  `self`) and defaults of `FakeCore.<name>` equal those of `carbon_room.core.<name>`.
- `test_fake_scenario_after_check`: start → ingest → calculate → check gives the four gaps G-1…G-4 with the
  owners and option keys in §3.16. Verified is 0, excluded is 29184, coverage is 0.
- `test_fake_resolutions_follow_table`: each row of the §3.16 summary table, in order.
- `test_fake_resolution_order_independent`: G-4 approve then G-2 pick A gives verified 14980.
- `test_fake_role_and_message_guards`: guest resolve raises `NotAllowed`; priya publish raises `NotAllowed`; an
  empty message id raises `NeedsRoomEvent`; upload without a path raises `ValueError`; resolving twice raises
  `ValueError`.
- `test_fake_threads`: `record_gap_thread` then `gap_for_thread` returns the gap; a second root for the same gap
  is a no-op; reusing a root raises `ValueError`.
- `test_fake_explain_before_and_after_upload`: the exact strings from §3.16.
- `test_async_core_runs_in_worker_thread`: a function recording `threading.get_ident()` differs from the loop
  thread.
- `test_async_core_rejects_unknown_name`: `AsyncCore(x).connect` raises `AttributeError`.
- `test_async_core_propagates_exceptions`: `fail["summary"] = NotFound("x")`, and awaiting raises `NotFound`.
- `test_frames_kind_and_fields_both_envelopes`: `{"type":"ping"}` → ping. `{"event":"message","data":{…},"id":7}`
  → message, sequence 7. `{"event":"evicted","data":{"code":"heartbeat_lapsed"}}` → evicted with fields
  `{"code":…}`. Garbage → None.
- `test_pong_payload`: `json.loads(pong(42)) == {"type": "pong", "cursor": 42}`.
- `test_fake_room_ids_and_queries`.
- `test_p3_code_never_imports_ledger`: scan `carbon_room/room/*.py` and the P3 agent modules
  (`orchestrator`, `gaps`, `resolution`, `publish`, `reports`, `ask`, `notices`, `hooks`, if present) for
  `carbon_room.ledger`, `from carbon_room import ledger` and `import tests` / `fakes`.

**Done when:**
- [ ] `test_core_signatures` passes against the fake too.
- [ ] The fake lives only under `tests/`.
- [ ] All the tests above pass.

### S02 · Grammar parser
**Stories:** 3.1 · **Wave:** 1 · **Depends on:** S01 (for `AGENT_NAMES`)
**Read:** contracts §8; plan §3.6; story 3.1.
**Files:**
- Create `carbon_room/room/grammar.py` and `tests/room/test_grammar.py`.
- Create `docs/proposals/002-room-help-command.md`. P3 owns contracts §8, and this proposal adds the `@<agent> help` row. Its four headings are Problem, Change, Who is affected and Decision; the decision is P3's.
**Produces:** §3.6.

**Behaviour (beyond §3.6):**
- The `S-` tag is normalised to `S-%03d` from 1–3 digits, with or without the dash, in any case.
- A known command with bad arguments becomes `help` with a reason:
  - an unknown month: `I don't know the month '<word>'.`
  - a missing tag: `Which source tag? Copy one from the draft.`
  - extra words after `close <Month> [<YYYY>]`: `Try: @carbon-room close October 2026`

  These reason strings must not contain a literal `S-<digits>` or `YYYY-MM` (§2).
- `parse` never raises. An empty body with no mention gives `ignore`, or `gap.reply` with `text ""` when
  `in_thread`, which is the attachment-only reply.

**Tests:** at least 30 table-driven cases with `today=date(2026, 11, 5)`, via `@pytest.mark.parametrize`.
Include at least these:

| body | in_thread | expected |
|---|---|---|
| `@carbon-room close October` | F | close.start `2026-10` |
| `@Carbon-Room   CLOSE   oct 2026` | F | close.start `2026-10` |
| `@carbon-room close December` | F | close.start `2025-12` |
| `@carbon-room close 2026-09` | F | close.start `2026-09` |
| `@carbon-room close Sept` | F | close.start `2026-09` |
| `@carbon-room close Smarch` | F | help, reason mentions `Smarch` |
| `@carbon-room close October please` | F | help (Try: …) |
| `@carbon-room status` / `@carbon-room, status` / `@carbon-room: status` | F | close.status |
| `` `@carbon-room` status `` | F | close.status |
| `@carbon-room resume` | F | close.resume |
| `@carbon-room publish` | F | close.publish |
| `@carbon-room help` and `@carbon-room` | F | help, reason None |
| `@reporter draft` | F | report.draft, target reporter |
| `@reporter trace S-014` / `s-14` / `S14` | F | report.trace `S-014` |
| `@reporter trace` | F | help |
| `@reporter verify audit` | F | audit.verify |
| `@reporter publish` | F | ask, target reporter |
| `@collector what is Warehouse-2 October electricity?` | F | ask, question text preserved |
| `@watchdog why is G-2 open?` | F | ask (G-2 not at the start) |
| `G-2 pick A` / `g-2 PICK a` | F | gap.fallback `G-2`, text `pick A` / `PICK a` |
| `@watchdog G-3 approve` | F | gap.fallback `G-3` `approve` |
| `G-2 pick A` | T | gap.fallback |
| `G-2` | F | ignore |
| `pick a` | T | gap.reply `pick a` |
| `Approved.` | T | gap.reply |
| `` (empty) | T | gap.reply `""` |
| `@watchdog approve` | T | gap.reply `approve` |
| `@watchdog what does this mean?` | T | ask, target watchdog |
| `hello everyone` | F | ignore |
| `@someone-else status` | F | ignore |

Plus `normalize_reply` cases:

| text | expected |
|---|---|
| `Pick a` | `("pick a", "")` |
| `pick A!` | `("pick a", "")` |
| `pick option b` | `("pick b", "")` |
| `Approved.` | `("approve", "")` |
| `Reject: wrong period` | `("reject", "wrong period")` |
| `rejected — duplicate` | `("reject", "duplicate")` |
| `upload Bill_Oct.pdf` | `("upload", "Bill_Oct.pdf")` |
| `UPLOAD` | `("upload", "")` |
| `hello` | `("hello", "")` |

**Done when:**
- [ ] Every row of contracts §8 has at least one passing case.
- [ ] An unknown command gives `ask`.
- [ ] "pick a" means `pick A`, and "approved" counts as `approve`.

### S03 · Identity and `people.yaml`
**Stories:** 3.2, 1.9 (template) · **Wave:** 1 · **Depends on:** S01
**Read:** contracts §2 (`Actor`) and §9 (`people.yaml`); `carbon_room/config.py`; plan §3.7.
**Files:**
- Create `carbon_room/room/identity.py`, `config/people.yaml` and `tests/room/test_identity.py`.
- Create `docs/proposals/001-people-username.md`, a P3-owned §9 addition with all four headings.

`config/people.yaml` holds the four §9 people with `username: ""` and `switch_ids: []`. M3 fills them in.

**Tests:**
- `test_known_person_maps_to_role`: `@switch-user-priya:test` → `Actor("human", "priya", "Priya",
  "site_manager")`.
- `test_unknown_sender_is_guest`.
- `test_agent_sender_maps_to_agent`, through `agent_ids`.
- `test_display_prefers_username`, with a fallback to the name, then the id.
- `test_is_known`.
- `test_placeholders_flags_empty_lead_and_priya`, and an `<…>` placeholder.
- `test_repo_people_yaml_parses_and_has_four_people`.

**Done when:**
- [ ] Known, guest and agent cases are tested.
- [ ] Every demo human has a role.

### S04 · Errors people can act on
**Stories:** 3.5 · **Wave:** 1 · **Depends on:** S01
**Read:** contracts §2 (exceptions); plan §3.8.
**Files:** Create `carbon_room/room/errors.py` and `tests/room/test_errors.py`.

**Tests:**
- One test per row of §3.8, with exact text.
- `test_generic_error_id_is_8_hex_and_logged`, via `caplog` at ERROR including the id.
- `test_needs_room_event_logged_as_bug`.
- `test_error_text_never_contains_traceback_or_key`.

**Done when:**
- [ ] Every exception type in contracts §2 has a tested message.

### S05 · Message templates
**Stories:** 5.1 · **Wave:** 1 · **Depends on:** S01 (uses the fake scenario objects in tests)
**Read:** contracts §2, §6, §8; plan §3.9 and §3.16; story 5.1.
**Files:** Create `carbon_room/room/messages.py` and `tests/room/test_messages.py`.

**Behaviour.**
- The spec writer turns §3.9's starting copy into exact strings.
- Short sentences and plain words. No emoji. Markdown limited to `**bold**`, `` `code` ``, `> quote` and `- `
  lists, all of which Mattermost renders.
- Templates never call core and never read config. Site and person names come in as arguments.
- Option labels and evidence are printed verbatim.

**Tests:**
- One snapshot test per function, with the exact expected string inline in the test, built from the §3.16 fake
  objects (`FakeCore` after `check`).
- `test_gap_root_conflict_shows_both_excerpts_and_both_options`, the story's Done-when case.
- `test_gap_root_without_options_is_informational`.
- `test_gap_root_fallback_hint`.
- `test_summary_post_numbers_are_formatted_from_summary`: `Decimal("3600")` → `3.6 tCO2e`, coverage 12 → `12%`.
- `test_t_rounding_half_up`: `Decimal("50")` → `0.1 tCO2e` and `Decimal("49")` → `0.0 tCO2e`.
- `test_t_handles_none_and_large`.
- `test_month_label_and_month_of`.
- `test_trace_card_sha_is_12_chars`.
- `test_total_moved`.
- `test_audit_result_ok_and_broken`.
- `test_messages_module_has_no_compute_calls`, a static check that `messages.py` never calls `sum(` or uses
  `/ 1000` outside `t`.

**Done when:**
- [ ] Each template has a snapshot test.
- [ ] The diesel conflict's gap root shows both excerpts and both options.

### S06 · Settings and event decoding
**Stories:** 2.2, plus env config · **Wave:** 1 · **Depends on:** S01
**Read:** plan §1.5, §3.2, §3.5 and §3.10; `.env.example`.
**Files:**
- Create `carbon_room/room/settings.py` and `carbon_room/room/events.py`.
- Create `tests/room/test_settings.py`, `tests/room/test_events.py` and `tests/room/fixtures/frames/*.json`.
- Modify `.env.example`: add every §3.10 variable with a comment; keep P1's lines.
- Fill the `## S06 events` section of `docs/switch-protocol-notes.md`.

**Fixtures** are documented-shape frames. Each is labelled `"_source": "docs"` until M2 replaces it with a
captured frame (`"_source": "captured"`):
- `message_top.json`, `message_thread_reply.json` and `message_with_attachment.json`
- `message_from_own_agent.json` (`sender_name` "watchdog")
- `command.json`, `room_join.json`, `ping.json`, `connection_state.json`, `evicted.json` and
  `message_no_id.json`

**Tests:**
- `test_decode_top_level_message`: every field, with `in_thread` False.
- `test_decode_thread_reply`: `in_thread` True, and `thread_id` equals the root id.
- `test_decode_attachment_fields`.
- `test_decode_drops_own_agents_by_id_and_name`.
- `test_decode_skips_command_and_control`.
- `test_decode_room_join`.
- `test_decode_malformed_returns_none`, for a missing payload and a missing `message_id`.
- `test_env_name`.
- `test_load_settings_reads_all_fields`.
- `test_load_settings_missing_lists_every_name`.
- `test_bool_flags_parse`.
- `test_env_example_lists_every_variable`.

**Done when:**
- [ ] Fixtures for `message`, `command`, `room_join` and a control frame each decode, or are skipped, correctly.

### S07 · Agent connection and fake Switch server
**Stories:** 2.1, 8.2 (server part) · **Wave:** 1 · **Depends on:** S01
**Read:** plan §1.5 (WebSocket, frames, heartbeat), §3.2 and §3.12; story 2.1 and story 8.2.
**Files:**
- Create `carbon_room/room/connection.py`, `tests/fakes/fake_switch.py` and `tests/room/test_connection.py`.
- Fill the `## S07 connection` section of `docs/switch-protocol-notes.md`.

**Behaviour:**
1. **URL and headers.** `http`→`ws` and `https`→`wss` on `{server}/agents/{agent_id}/connection/ws`. Query
   parameters:
   - `connection_id`: a uuid4 kept for the object's life
   - `rooms`: comma-joined
   - `filter`
   - `client=carbon-room-python` and `client_version`
   - `start_from` and `expected_generation`, only once known

   Header: `Authorization: Bearer <key>`. Use `websockets.asyncio.client.connect(url,
   additional_headers=..., ping_interval=None)`, so the client does not send its own WebSocket pings.
2. **First frame** must be `connection_state`.
   - Store `generation`. Set `cursor` to `max(cursor, state cursor)` when present.
   - Log one INFO line: `connected agent=<name> rooms=<ids> filter=<filter>`.
   - Set `connected`.
   - Reset the backoff.
3. **Read loop.**
   - `ping`: send `frames.pong(cursor or 0)` immediately, before anything else.
   - Domain frame: if `sequence <= cursor`, skip it (a duplicate). Otherwise set `cursor = sequence` and call
     `on_event(agent_name, frame)`. The callback is synchronous and non-blocking; never await it.
   - `gap`: set `cursor = resumed_at`.
   - `refused`: log `status` and `detail`.
   - `evicted`: log `code` and `reason`. Stop for good on `taken_over` or `closed`. Otherwise reconnect.
4. **Close codes.**
   - 4401: raise `AuthError` from `run()`, with no retry.
   - 4400, 4403 and 4409: log and stop.
   - Anything else, including 1000, 1011, 1012 and a network error: reconnect with the same `connection_id`,
     `start_from=cursor` and `expected_generation`, sleeping `backoff_delays()` between attempts.
5. **`stop()`** closes the socket, and `run()` returns within 1 s.
6. **Logging.** Never log the key or headers.

**Fake Switch (tests/fakes/fake_switch.py).**

```python
FakeSwitch(*, ping_interval=2.0, evict_after=6.0, control_style="type")
```

| Method | Behaviour |
|---|---|
| `await start() -> str` | Serves on `127.0.0.1:0`; returns `http://127.0.0.1:<port>` |
| `await stop()` | Shuts the server down |
| `await inject(agent_id, payload, *, room_id="room-1", kind="message") -> int` | Wraps the payload in the documented envelope, assigns the next sequence, buffers it, and sends it if that agent is connected |
| `await drop(agent_id, code=1012)` | Closes that agent's socket from the server side |
| `await evict(agent_id, code="heartbeat_lapsed")` | Sends `evicted`, then closes with code 1000 |
| `connections: list[Record]` | Each `Record` has `agent_id`, `query: dict`, `auth: str \| None`, `pongs: list[tuple[float, int]]` and `pings_sent: list[float]` |
| `message(...)` static | Builds a `message` payload |

On connect, the fake:
- closes with 4401 if there is no `Bearer` header
- sends `connection_state` (`generation` increments per open; `cursor` is the last sequence)
- replays buffered events with sequence > `start_from`
- pings every `ping_interval`
- evicts with `heartbeat_lapsed` after `evict_after` seconds without a pong

`control_style` "type" sends `{"type": "ping"}`; "event" sends `{"event": "ping", "data": {}}`.

**Tests** (real localhost sockets, `ping_interval=0.2`, `evict_after=0.6`):
- `test_sends_auth_and_query`.
- `test_first_frame_sets_generation_and_cursor`.
- `test_pong_within_200ms_even_while_worker_thread_sleeps`: a `run_in_executor(time.sleep, 1)` is in flight.
- `test_pong_cursor_is_highest_sequence`.
- `test_events_delivered_in_order_and_duplicates_skipped`.
- `test_server_drop_reconnects_with_same_id_and_cursor_no_loss`: inject 3, drop, inject 2 while disconnected,
  and receive all 5 exactly once.
- `test_evicted_heartbeat_reconnects`.
- `test_evicted_taken_over_stops`.
- `test_4401_raises_auth_error_without_retry`.
- `test_gap_frame_moves_cursor`.
- `test_both_control_styles`, parametrized.
- `test_backoff_sequence`.
- `test_stop_returns_quickly`.
- `test_key_never_logged`.

The suite stays under 15 s.

**Done when:**
- [ ] Against the fake Switch server, pongs are sent within 200 ms.
- [ ] A server-side close leads to a reconnect without lost events.

### S08 · Ops client (written after spike M2)
**Stories:** 2.3 · **Wave:** 2 · **Depends on:** S06, M2 (`docs/switch-ops.json`, `docs/spikes.md`)
**Read:** plan §1.5 (Ops) and §3.11; `docs/switch-ops.json`; the S1, S5 and S6 sections of `docs/spikes.md`.
**Files:**
- Create `carbon_room/room/ops.py` and `tests/room/test_ops.py`.
- Fill the `## S08 ops` section of `docs/switch-protocol-notes.md`.

**Behaviour:**
1. **`call`** sends `POST {server}/agents/{id}/ops/{op}` with the args object unwrapped and headers
   `Authorization: Bearer`, `Content-Type: application/json`, and `X-Switch-Connection-Id` when set. It returns
   `response.json()["result"]`.
2. **Errors.** Any status of 400 or above raises `SwitchError(status, op, detail)`, where `detail` is the
   server's `detail` field, or the body text cut to 300 characters. The message format is
   `"<op> failed (<status>): <detail>"`.
3. **`list_ops`** sends `GET /agents/{id}/ops` and returns `["operations"]`. It caches the result.
4. **`post`** uses the exact `post_message` argument names recorded in M2.
   - If S1 failed and `thread_id` is given, it raises `SwitchError(None, "post_message", "threads unsupported")`.
   - The message id comes from the result key recorded in M2 (S5). If S5 failed, it falls back to
     `read_context(10)` and takes the newest message whose body equals the text.
   - If no id is found, it raises `SwitchError`.
5. **`send_targeted`**, **`read_context`** and **`upsert_room_doc`** use the exact names recorded in M2.
   - `upsert_room_doc` updates first. On a "not found" error it creates. On an "exists" error from create it
     updates. It returns False if spike S6 recorded documents as invisible or unsupported.
   - A `not_permitted` result from `send_targeted` logs a WARNING and does not raise.
6. **`download`** sends `GET` to the `SWITCH_MEDIA_PATH` template with `{agent_id}` and `{mxc}` filled in, and
   returns the bytes.

**Tests** (`httpx.MockTransport`):
- `test_call_headers_and_unwrapped_body`.
- `test_result_unwrapped`.
- `test_error_mapping_400_403_404_409`.
- `test_post_top_level_and_thread_args`.
- `test_post_returns_message_id`.
- `test_post_message_id_fallback_read_context` (only if S5 failed).
- `test_post_thread_unsupported_raises` (only if S1 failed).
- `test_send_targeted_not_permitted_logs`.
- `test_upsert_room_doc_create_then_update`.
- `test_download_bytes`.
- `test_list_ops_cached`.
- `test_key_never_logged`.

**Done when:**
- [ ] Unit tests with a mocked transport check the headers, the body and the error mapping.

### S09 · Agent registration CLI
**Stories:** 1.2 · **Wave:** 1, started after S06 merges · **Depends on:** S06 (`env_name`)
**Read:** plan §1.5 (Auth, registration, addressing) and §3.10; story 1.2.
**Files:**
- Create `carbon_room/room/register.py` and `tests/room/test_register.py`.
- Fill the `## S09 register` section of `docs/switch-protocol-notes.md`.

**CLI.** `python -m carbon_room.room.register [--env PATH] [--from-console DIR] [--room ROOM_ID]`. It uses
plain `httpx.Client`, not `OpsClient`, so it can merge before S08.
1. **Mode A** (default).
   - For each agent in `AGENT_NAMES`, skip it if `.env` already has both its ID and KEY: print
     `<name>: already registered, skipping`.
   - Otherwise send `POST {SWITCH_SERVER}/agents` with `Bearer SWITCH_REGISTRATION_KEY` and the body from
     §1.5. Use `connector_type "carbon-room-python"`, `connection_model "always_on"`, `message_exchange true`,
     empty mediation lists, `description` from a fixed per-agent map, and `display_name` from `AGENT_TITLES`.
   - On 200/201, write the ID and KEY with `dotenv.set_key`, and print `<name>: registered`. Never print the key.
   - On 409, print `<name>: name already taken. If it is yours, copy its id and key into .env (docs/setup-switch.md); otherwise delete it in the Gateway.`
   - On anything else, print the status and detail. The command exits 1 at the end if any agent failed.
2. **Mode B** (`--from-console DIR`) reads `DIR/<name>.json`, writes `SWITCH_AGENT_<NAME>_ID` and `_KEY`, and
   sets `SWITCH_SERVER` from `SWITCH_API_ENDPOINT` if it is unset.
3. **Addressing.** For each agent, send `POST …/ops/update_agent_detail {"agent_id", "addressing": "anyone"}`.
   - On 403 or 400, print `<name>: Switch refused addressing=anyone; set "Anyone" in Switch Console → agent settings.`
   - Never fail the run because of this.
4. **Room invite** (when `--room` or `SWITCH_ROOM_ID` is set). Read the `invite_agent_to_room` schema from
   `GET /ops`, call it for each agent, and on any failure print
   `<name>: invite it to the room in Switch Console.`
5. **Idempotent.** A second run makes zero `POST /agents` calls and the same addressing and invite calls.

**Tests** (`MockTransport` and a tmp `.env`):
- `test_first_run_registers_four_and_writes_env`.
- `test_second_run_skips_all`.
- `test_409_message_and_continue`.
- `test_other_error_exit_code_1`.
- `test_from_console_imports_files`.
- `test_addressing_refused_prints_console_hint`.
- `test_invite_failure_prints_hint`.
- `test_key_never_printed_or_logged`, via `capsys` and `caplog`.

**Done when:**
- [ ] Running it twice is safe.
- [ ] Manual check: all four agents appear as participants in `emissions-reporting`.

### S10 · Dispatcher and worker lanes
**Stories:** 2.4, plus P1's replay-protection ask · **Wave:** 2 · **Depends on:** S01, S02, S06
**Read:** plan §2, §3.4, §3.5, §3.6 and §3.13; story 2.4; `docs/HANDOFF.md` (P3 security asks).
**Files:** Create `carbon_room/room/dispatch.py` and `tests/room/test_dispatch.py`.
**Behaviour:** §3.13 exactly.
- The handled-id set is a bounded `OrderedDict` that evicts the oldest entries past `seen_limit`.
- `submit` never blocks; it uses `put_nowait` on an unbounded queue.
- `stop()` lets the in-flight mutation finish, then cancels any pending read tasks.

**Tests** (fake `decode`, `classify` and `handle` that record calls):
- `test_slow_core_call_does_not_delay_loop`: the handler awaits `AsyncCore(FakeCore(delay=1.0))`, and a probe
  coroutine ticking every 50 ms never lags more than 200 ms.
- `test_two_resolves_same_close_run_in_order`: the second starts after the first ends, in submission order.
- `test_reads_run_concurrently_with_mutation`.
- `test_duplicate_message_id_handled_once`, for the same id from two agents and for a replay after reconnect.
- `test_ignored_copy_does_not_block_addressed_copy`: the watchdog copy is classified ignore, then the
  carbon-room copy is handled.
- `test_other_room_dropped`.
- `test_non_message_dropped`.
- `test_handler_exception_goes_to_on_error`.
- `test_on_error_failure_is_logged_not_raised`.
- `test_seen_limit_evicts_oldest`.
- `test_stop_waits_for_inflight_mutation`.

**Done when:**
- [ ] A 5-second fake core call doesn't delay a pong. The loop-lag probe shows this; S07 covers the socket.
- [ ] Two resolves for the same close run in order.

### S11 · Router and attachments
**Stories:** 3.3, 3.4, 2.6 · **Wave:** 2 · **Depends on:** S01, S02, S06
**Read:** contracts §6 and §8; plan §3.6 (`normalize_reply`) and §3.14; stories 3.3, 3.4 and 2.6;
`docs/HANDOFF.md` (managed attachment root, 10 MiB, no symlinks).
**Files:**
- Create `carbon_room/room/router.py` and `carbon_room/room/attachments.py`.
- Create `tests/room/test_router.py` and `tests/room/test_attachments.py`.

**Router behaviour:**
1. A RESOLVED gap gives `NoMatch("gap_resolved")`. A gap with no options gives `NoMatch("no_options")`.
2. An attachment on a gap with an `upload` option gives `GapAction(upload option, payload=dict(option.params),
   filename=None)`.
3. Otherwise `key, rest = normalize_reply(text)` is compared with `option.key.lower()`.
   - On a match, the payload is a copy of `option.params`.
   - For `reject`, a non-empty `rest` adds `payload["reason"]`.
   - For `upload`, `filename = rest or None`.
4. Anything else gives `NoMatch("unknown_reply")`.
5. `find_gap` ignores case: `g-2` finds `G-2`.

**Attachment behaviour:**
1. **`safe_name`** keeps only the basename and maps characters outside `[A-Za-z0-9._-]` to `_`. It raises
   `AttachmentMissing` on an empty name, `.`, `..` or a leading dot.
2. **`download` mode** with an attachment:
   - Get the bytes. If there are more than `MAX_BYTES`, raise
     `AttachmentMissing("That file is over 10 MiB, so I can't take it.")`.
   - Write `inbox_dir / f"{safe_name(message_id)}_{safe_name(filename)}"` with exclusive create
     (`open(..., "xb")`), after `mkdir(parents=True)`.
   - A download error falls back to inbox mode.
3. **`inbox` mode.**
   - The name is `typed_name`, else `attachment.filename`, and goes through `safe_name`.
   - The candidate must exist, be a regular file and not a symlink, resolve inside `inbox_dir`, and be at most
     `MAX_BYTES`.
   - Otherwise raise `AttachmentMissing("I can't see that file yet. Put it in data/inbox/ and reply upload
     {name}.")`, where `{name}` is the name, or `<name>` when there is none.

**Tests:**
- `test_pick_a_in_diesel_gap_gives_option_a_params`.
- `test_hello_gives_unknown_reply`.
- `test_reject_reason_in_payload`.
- `test_attachment_counts_as_upload`.
- `test_upload_typed_name`.
- `test_resolved_and_optionless`.
- `test_find_gap_case_insensitive`.
- `test_safe_name_traversal_and_unicode`: for example `../../etc/passwd` → `passwd`, and `bill (1).pdf` →
  `bill__1_.pdf`.
- `test_download_mode_writes_managed_file`.
- `test_download_too_big`.
- `test_download_failure_falls_back_to_inbox`.
- `test_inbox_mode_finds_file`.
- `test_inbox_missing_gives_exact_text`.
- `test_inbox_rejects_symlink`.
- `test_inbox_rejects_oversize`.

**Done when:**
- [ ] "Pick a" in the diesel thread maps to option A's params.
- [ ] "hello" maps to an options reply (the handler side is in S13).
- [ ] `G-2 pick A` routes with and without a thread (the parse side is in S02; the S13 test covers the rest).
- [ ] Both attachment paths are tested.

### S12 · Close flow: orchestrator and gap roots
**Stories:** 4.1, 4.2, 4.3, 4.4 · **Wave:** 3 · **Depends on:** S01, S05
**Read:** contracts §4, §7 (phases, totals) and §10; plan §3.3, §3.9, §3.15 and §3.16; stories 4.1–4.4;
`carbon_room/config.py` (`load_sites`, `load_config`).
**Files:**
- Create `carbon_room/agents/orchestrator.py` and `carbon_room/agents/gaps.py`.
- Create `tests/room/test_orchestrator.py` and `tests/room/test_gaps.py`.

**Interfaces:**

```python
# gaps.py
async def post_new_gaps(ctx: Context, close_id: str, findings: list[Finding]) -> list[str]

# orchestrator.py
class CloseState(TypedDict):
    close_id: str; month: str; site_ids: list[str]; factor_set: str; findings: list[dict]
def build_close_graph(ctx: Context) -> CompiledStateGraph
async def handle_close_start(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None
```

**Behaviour:**
1. **Setup.** `month = intent.args["month"]`, `site_ids` comes from `config.load_sites()` in file order, and
   `factor_set = config.load_config()["default_factor_set"]`.
   - If the config is missing, raise `ValueError("config/carbon_room.yaml is missing; P2 provides it")`, which
     `app.on_error` maps (§3.8).
   - Site names come from `config.site(id)["name"]`.
2. **Start.** `close_id = await ctx.core.start_close(month, site_ids, factor_set, actor, event.message_id)`, then
   `ctx.room.begin_close(close_id)`.
3. **Graph.** `StateGraph(CloseState)` with nodes `plan → collect → calculate → check → post_gaps → summary →
   END`, compiled with `MemorySaver()`. Invoke it with `ainvoke(state, {"configurable": {"thread_id":
   close_id}})`. The nodes are closures over `ctx`, and the state holds only JSON-safe values (findings via
   `dataclasses.asdict`).
   - **plan:** carbon-room posts `close_plan`.
   - **collect:**
     - `send_targeted("carbon-room", "collector", handoff_collect(...))`
     - `report = await core.ingest(close_id, Actor("agent", "collector", "Collector"))`
     - collector posts `collector_statement(report)`
     - `await ctx.on_phase_end(close_id)`
   - **calculate:** `await core.calculate(close_id)`, then `on_phase_end`.
   - **check:** `send_targeted("carbon-room", "watchdog", handoff_check(...))`, then
     `findings = await core.check(close_id)`.
   - **post_gaps:** `await post_new_gaps(ctx, close_id, findings)`.
   - **summary:** `s = await core.summary(close_id)`, then carbon-room posts `summary_post(month_label, s,
     ctx.display)` and `on_phase_end`.

   The LangGraph lever: if checkpointing fights the async closures for more than 2 hours, replace the graph with
   the same node functions called in sequence. Keep `build_close_graph`'s signature and note the change in the
   PR's Deviations section.
4. **`post_new_gaps`.**
   - `_, open_gaps = await core.resume_state(close_id)`.
   - For each gap with `thread_root_message_id is None`, in gap-number order: watchdog posts `gap_root(gap,
     finding_by_id.get(gap.finding_id), ctx.display(gap.owner), fallback_hint=not ctx.threads)`, then
     `await core.record_gap_thread(close_id, gap.gap_id, message_id)`.
   - It returns the posted gap ids, and never posts a gap that already has a root.

**Tests** (`ctx` fixture with `FakeCore` and `FakeRoom`):
- `test_close_october_posts_plan_statement_roots_summary_in_order`: the top-level agents are
  `[carbon-room, collector, watchdog×4, carbon-room]`, with exact texts from `messages`.
- `test_handoffs_are_targeted`: two targeted messages from carbon-room, to collector and to watchdog.
- `test_three_agent_names_post`.
- `test_start_close_gets_event_message_id_and_actor`.
- `test_core_call_order`.
- `test_gap_roots_recorded_in_core`.
- `test_post_new_gaps_twice_posts_once`.
- `test_summary_post_equals_summary_output`.
- `test_on_phase_end_called_after_collect_calculate_summary`.
- `test_missing_config_raises_value_error`.
- `test_fallback_hint_when_threads_off`.

**Done when:**
- [ ] Against the fake core, `close October` posts the plan, the collector statement, the gap roots and a
  summary, in that order.
- [ ] Three agent names post.
- [ ] Each root is posted once.
- [ ] The summary's numbers equal `summary()`.

### S13 · Resolution, publish, reports and ask
**Stories:** 4.5, 4.6, 5.4, plus status, trace, audit and help · **Wave:** 3 · **Depends on:** S04, S11, S12
**Read:** contracts §4, §6 and §7; plan §3.8, §3.9, §3.14, §3.15 and §3.16; stories 4.5, 4.6 and 5.4.
**Files:**
- Create `carbon_room/agents/resolution.py`, `carbon_room/agents/publish.py`, `carbon_room/agents/reports.py`
  and `carbon_room/agents/ask.py`.
- Create `tests/room/test_resolution.py`, `tests/room/test_publish.py`, `tests/room/test_reports.py` and
  `tests/room/test_ask.py`.

**`handle_gap_reply`:**
1. **Find the gap.**
   - For `gap.reply`: `gap = await core.gap_for_thread(event.thread_id)`. If it is None, return silently.
   - For `gap.fallback`: `close_id = await core.latest_close()`. If it is None, reply with `no_close()`.
     Otherwise get `_, open_gaps = await core.resume_state(close_id)` and `gap = router.find_gap(open_gaps,
     intent.args["gap_id"])`. If none is found, reply `gap_not_found(gap_id)`.
2. **Where replies go.** All of them go to `gap.thread_root_message_id or event.thread_id or event.message_id`,
   as watchdog.
3. **Guests** (`actor.role is None`) get `reply_for(NotAllowed(...), owner_name=ctx.display(gap.owner)).text`,
   and core is not called.
4. **Match.** `router.match_reply(gap, intent.args["text"], bool(event.attachments))`.
   - `unknown_reply` → `options_help`
   - `gap_resolved` → `already_resolved`
   - `no_options` → `no_reply_needed()`
5. **Resolve.**
   - Post `checking()`.
   - For an upload, `payload["path"] = str(await attachments.fetch(message_id=event.message_id,
     attachment=event.attachments[0] if event.attachments else None, typed_name=action.filename,
     mode=ctx.attachments_mode, inbox_dir=ctx.inbox_dir, download=ctx.download))`. On `AttachmentMissing`,
     reply with its text and stop.
   - `before = await core.summary(close_id)`.
   - `findings = await core.resolve(gap.gap_id, option.action, actor, event.message_id, payload)`.
6. **Outcome.** `_, open_after = await core.resume_state(close_id)`.
   - If the gap is no longer open, reply `outcome_resolved`.
   - Otherwise reply `outcome_open(gap, reason)`. The reason is the title of the finding in `findings` with the
     same `finding_id`, else `the next check still flags it`.
7. **Follow-up.**
   - `await gaps.post_new_gaps(ctx, close_id, findings)`.
   - `after = await core.summary(close_id)`. If `verified_kgco2e` or `coverage_pct` changed, carbon-room posts
     `total_moved(before, after)` at top level with `essential=False`.
   - `await ctx.on_phase_end(close_id)`.
8. **Errors.** `CarbonRoomError` and `ValueError` raised by core are caught and replied in the gap thread with
   `reply_for(exc, owner_name=ctx.display(gap.owner))`. Other exceptions propagate to `app.on_error`.

**`publish.py`:**
- **`handle_draft`:** `close_id = latest_close()` (if None, reply `no_close`), then
  `report = await core.draft_report(close_id)`. Reporter posts `draft(report, month_label)` at top level.
- **`handle_publish`:**
  - A guest is refused in the thread, and core is not called.
  - `phase, _ = resume_state`. If the phase is not DRAFTED, call `draft_report` first.
  - `report = await core.publish(close_id, actor, event.message_id)`.
  - `paths` are the files under `ctx.out_dir / month_of(close_id) / f"v{report.version}"`, sorted and relative
    to the repo; the list is empty if the directory is missing.
  - carbon-room posts `published(report, ctx.display(actor.id), paths)`.
  - `NotAllowed` from core is replied in the command's thread with `reply_for(exc)`.

**`reports.py`** (all of these reply in the command's thread):
- `handle_status` posts `summary_post`.
- `handle_trace` posts `trace_card(tag, ctx.room.link(tag.chat_message_id) if tag.chat_message_id else None)`.
  `NotFound` replies `tag_not_found(tag)`.
- `handle_verify_audit` posts `audit_result`.
- `handle_help` posts `help_text(intent.args.get("reason"))`.

Any handler that finds no close replies `no_close()`.

**`ask.py`:** `handle_ask` replies with `no_close()` when there is no close. Otherwise it posts `await
core.explain(close_id, question, actor)` verbatim, in the question's thread, as `intent.target_agent`.

**Tests** (fake scenario; events built with a helper `make_event(body, thread_id=None, sender=lead_id,
attachments=())`):
- `test_pick_a_in_diesel_thread_calls_resolve_with_option_a`: `resolve("G-2", "pick", lead, msg_id,
  {"claim_id": "CL-0003"})`.
- `test_hello_in_gap_thread_lists_options_and_no_resolve`.
- `test_fallback_in_channel_routes_and_replies_in_gap_thread`.
- `test_guest_refused_without_core_call`.
- `test_upload_with_inbox_file_passes_path`.
- `test_upload_missing_file_exact_text`.
- `test_outcome_resolved_and_still_open`.
- `test_new_gaps_from_resolve_are_posted`.
- `test_total_moved_posted_once_when_changed`.
- `test_reject_posts_no_total_line`.
- `test_four_scripted_resolutions_reach_fake_final_totals`: 22.9 t and 100%, with four "total moved" lines.
- `test_resolve_error_replied_in_thread`.
- `test_draft_posts_headline`.
- `test_lead_publishes_and_paths_listed`, with a tmp `out_dir` holding files.
- `test_guest_publish_refused`.
- `test_priya_publish_not_allowed_text`.
- `test_publish_drafts_first_when_needed`.
- `test_trace_card_and_unknown_tag`.
- `test_verify_audit_reply`.
- `test_status_reply_in_thread`.
- `test_ask_unknown_before_upload_names_priya`.
- `test_ask_verified_after_upload`.
- `test_no_close_replies`.

**Done when:**
- [ ] Against the fake core, the four scripted resolutions move the total to the fake final figure. The
  real-core version is S18.
- [ ] An unchanged total posts no top-level line.
- [ ] A lead can publish, and a guest gets a clear refusal.
- [ ] The ask answer is UNKNOWN naming Priya before the upload, and a verified figure after it.

### S14 · Room hygiene: resume, budget notices, noise guard, Close Board
**Stories:** 4.7, 4.8, 5.3, 5.2 · **Wave:** 3 · **Depends on:** S12
**Read:** contracts §4 (`resume_state`, `budget_usage`) and §9 (`noise`, `budgets`); plan §3.3, §3.9 and §3.16;
stories 4.7, 4.8, 5.2 and 5.3.
**Files:**
- Modify `carbon_room/agents/orchestrator.py` to add the resume functions.
- Create `carbon_room/agents/notices.py`, `carbon_room/agents/hooks.py`, `carbon_room/room/noise.py` and
  `carbon_room/room/board.py`.
- Create `tests/room/test_resume.py`, `tests/room/test_notices.py`, `tests/room/test_noise.py` and
  `tests/room/test_board.py`.

**Interfaces:**

```python
# orchestrator.py (added)
async def resume(ctx, close_id: str) -> None
async def handle_resume(ctx, event, intent, actor) -> None
async def resume_on_startup(ctx) -> bool

# notices.py
async def check_budgets(ctx, close_id: str) -> list[str]   # returns the notices posted

# hooks.py
async def after_phase(ctx, close_id: str) -> None           # board, then budgets; never raises

# noise.py
class NoiseGuard:                                           # implements Room
    def __init__(self, inner: Room, *, max_posts: int = 12, reserve: int = 2) -> None
    top_level_count: int

# board.py
BOARD_NAME = "close-board"
async def update_board(ctx, close_id: str) -> bool
```

**Behaviour:**
1. **`resume`.**
   - `phase, gaps = resume_state(close_id)`.
   - carbon-room posts `resume_line(month_label, phase, gaps, ctx.display, ctx.room.link)` at top level.
   - Then `post_new_gaps(ctx, close_id, [])`, which only posts gaps that have no root, without evidence.
   - It **never** reposts an existing root.
2. **`handle_resume`** replies `no_close()` when there is no close; otherwise it calls `resume`.
3. **`resume_on_startup`** resumes and returns True if `latest_close()` exists and its phase is not PUBLISHED.
4. **`check_budgets`.**
   - `usage = await core.budget_usage(close_id)`.
   - For each agent, sorted, whose `state` is `warn` or `stopped` and whose key `(close_id, agent, state)` is
     not in `ctx.state.setdefault("budget_notices", set())`: post `budget_warn` or `budget_stopped` as
     carbon-room, top level, `essential=False`, then record the key.
   - `warn_label` is formatted from `config.load_config().get("budgets", {}).get("warn_at", 0.8)`, giving "80%".
5. **`NoiseGuard`.**
   - Thread posts pass through and are not counted. `begin_close` resets the count and the buffer.
   - A non-essential top-level post, once `count >= max_posts - reserve`, is buffered: log a WARNING and return
     `""`.
   - The next essential top-level post is sent as `"\n".join(buffer) + "\n\n" + text`, and the buffer clears.
   - Essential posts always go out. If the count then exceeds `max_posts`, log a WARNING.
   - `max_posts` comes from config `noise.max_top_level_posts`, default 12.
6. **`update_board`.**
   - `s = await core.summary(close_id)`.
   - `ok = await ctx.room.upsert_doc("carbon-room", BOARD_NAME, board(month_label, s, ctx.display,
     ctx.room.link))`.
   - It returns `ok`. If `ok` is False (spike S6 failed), there is no fallback post, because the summary posts
     already carry the same figures; the story's fallback was cut for the noise budget.
7. **`after_phase`** runs `update_board`, then `check_budgets`. It logs and swallows every exception.

**Tests:**
- `test_resume_line_lists_open_gaps_with_links_and_posts_no_roots`: run the close, then use a new `FakeRoom` and
  the same `FakeCore`.
- `test_resume_posts_missing_root_once`.
- `test_resume_on_startup_true_false_published`.
- `test_budget_warn_once_then_stopped_once`, with `fake_core.budget` set between calls.
- `test_noise_full_scripted_close_at_most_12_top_level`: 7 essential, then 4 "total moved", then draft and
  publish, for 12 posts with the 4th "total moved" merged into the draft post.
- `test_noise_thread_posts_not_counted`.
- `test_noise_essential_always_sent`.
- `test_board_matches_summary_after_each_resolution`.
- `test_board_unsupported_returns_false_and_posts_nothing`.
- `test_after_phase_swallows_errors`.

**Done when:**
- [ ] Kill-and-restart (simulated: new room, same core) shows the resume line with the right gaps.
- [ ] With a tiny budget, the warning appears once.
- [ ] A full scripted close stays at or under 12 top-level posts.
- [ ] The board matches `summary()` after each of the four resolutions.

### S15 · App wiring, SwitchRoom, runner and end-to-end loop
**Stories:** 2.5, 8.2 (e2e test) · **Wave:** 4 · **Depends on:** S02–S14
**Read:** plan §2 and all of §3; stories 2.5 and 8.2; `docs/spikes.md`.
**Files:**
- Create `carbon_room/room/app.py`, `carbon_room/room/switch_room.py` and `carbon_room/room/run.py`.
- Create `tests/room/test_app.py`, `tests/room/test_switch_room.py`, `tests/room/test_room_loop.py` and
  `tests/room/test_run_guard.py`.

**Interfaces:**

```python
# app.py
HANDLERS: dict[str, Handler]   # §3.15
def classify(event: RoomEvent, *, today: date, single_agent: bool) -> Intent
async def handle(ctx, event, intent) -> None
async def on_error(ctx, event, intent, exc) -> None

# switch_room.py
class SwitchRoom:              # implements Room
    def __init__(self, clients: Mapping[str, OpsClient], *, single_agent: bool = False,
                 permalink_base: str | None = None, threads: bool = True) -> None

# run.py
def build(settings: Settings, *, core: Any, transport: httpx.AsyncBaseTransport | None = None) -> Runtime
async def amain(settings: Settings, *, core: Any = carbon_room.core) -> None
def main() -> int
```

`Runtime` holds `ctx`, `dispatcher`, `connections` and `clients`.

**Behaviour:**
1. **`classify`** is `grammar.parse` plus the acceptance rule in §3.13.
2. **`handle`** builds `actor = identity.actor_for(event.sender, event.sender_name)` and awaits
   `HANDLERS[intent.kind](ctx, event, intent, actor)`.
3. **`on_error`** posts `reply_for(exc, agent=intent.target_agent).text` in `event.thread_id or
   event.message_id`, as `intent.target_agent or "carbon-room"`.
4. **`SwitchRoom.post`** uses the agent's `OpsClient`.
   - In single-agent mode it uses carbon-room's client with the prefix `[{AGENT_TITLES[agent]}] ` for the other
     agents, and `send_targeted` becomes a logged no-op.
   - If `threads` is False and a `thread_id` is given, it posts top level with the prefix `↳ ` and logs at INFO.
   - `link` returns `f"{permalink_base}/{id}"`, or `f"message {id}"` when no base is set.
5. **`build`.**
   - One `AgentConnection` per agent (only carbon-room in single-agent mode). The filter is `all` for watchdog
     and in single-agent mode, `addressed` otherwise. `on_event` is `dispatcher.submit`.
   - One `OpsClient` per agent, sharing its connection's `connection_id`.
   - `ctx = Context(core=AsyncCore(core), room=NoiseGuard(SwitchRoom(...)), display=identity.display,
     on_phase_end=partial(after_phase, <ctx>), threads=…, attachments_mode=…, download=…)`.
6. **`amain`.**
   - `logging.basicConfig(INFO)`.
   - Start the dispatcher and all connections. Wait until every `connected` is set, with a 30 s timeout; on
     timeout, log which agent failed and exit 2.
   - Then `await resume_on_startup(ctx)`, then run until SIGINT or SIGTERM.
   - On shutdown, stop connections and the dispatcher, close the clients, shut down the executor, and return.
7. **`main`.**
   - Refuse to start (exit 3, with the message `refusing to run with test doubles loaded`) if any
     `sys.modules` key starts with `fakes` or `tests`.
   - Load settings; a `ValueError` exits 1 and lists the missing variables.
   - `asyncio.run(amain(settings))`, which always uses `carbon_room.core`.

**Tests:**
- `test_classify_acceptance_matrix`: addressed versus not, and the receiving agent versus the target, for each
  kind.
- `test_handlers_cover_every_intent_kind`.
- `test_on_error_replies_in_thread_as_target`.
- `test_switch_room_posts_via_right_client`.
- `test_single_agent_prefixes`.
- `test_threads_off_prefix`.
- `test_link_formats`.
- `test_room_loop_close_then_thread_reply_resolves`. This uses `FakeSwitch` from S07, ops through a
  `MockTransport` that hands out message ids, `FakeCore`, and real `build()`.
  1. Inject `@carbon-room close October` on carbon-room's socket (`addressed=True`) and on watchdog's
     (`addressed=False`).
  2. Wait for the summary post.
  3. Inject `pick A` with `thread_id` set to G-2's root id on watchdog's socket.
  4. Assert `FakeCore.calls` holds exactly one `start_close` and one `resolve("G-2", "pick", …)`, and that the
     outcome was posted in G-2's thread.

  This finishes in under 20 s.
- `test_main_refuses_with_fakes_loaded`.

**Manual check (real room):**
- `make run` shows four `connected …` lines.
- `@carbon-room status` with no close gets `no_close`, and only carbon-room replies.

**Done when:**
- [ ] `make run` shows four connected agents, and a message to `@carbon-room` is received by that agent only.
- [ ] The loop test passes in under 20 s with no real Switch.

### S16 · Makefile, `make doctor`, `make reset-demo`
**Stories:** 6.1, 6.2, 6.3 · **Wave:** 2 · **Depends on:** S03, S06; S08 for the room part of reset
**Read:** contracts §9 (`llm.mode`); plan §1.3 and §3.10; stories 6.1–6.3; `carbon_room/__main__.py`;
`carbon_room/sources/cache.py` (cache path only; do not import it).
**Files:**
- Create `Makefile`, `carbon_room/room/doctor.py`, `carbon_room/room/reset.py` and `scripts/reset_demo.sh`.
- Create `tests/room/test_doctor.py`, `tests/room/test_reset.py` and `tests/room/test_makefile.py`.

**Makefile.**
- `PY ?= .venv/bin/python`. Every recipe starts with an `@echo "→ <what it does>"`.
- Targets:

| Target | Recipe |
|---|---|
| `help` | Lists the targets |
| `setup` | Creates `.venv` if missing, then `$(PY) -m pip install -e . pytest ruff` |
| `seed` | `$(PY) scripts/make_seed.py` |
| `register` | `$(PY) -m carbon_room.room.register` |
| `doctor` | `$(PY) -m carbon_room.room.doctor` |
| `run` | `$(PY) -m carbon_room.room.run` |
| `reset-demo` | `scripts/reset_demo.sh` |
| `test` | `$(PY) -m pytest -q` |
| `lint` | ruff on the P3 paths |
| `refresh-cache` | Prints "needs P1's live-extraction command" until P1 provides one |

**Doctor.**

```python
Check(name: str, ok: bool, detail: str, fix: str)
run_checks(*, env, runner=subprocess.run, transport=None, repo_root=Path("."))
main() -> int
```

`main` prints `✓ <name>`, or `✗ <name> — <detail>` followed by `    fix: <fix>`, and exits 1 if anything failed.
The checks run in order, with exact names:
1. **Docker is running**: `docker info` exits 0. Fix: `Start Docker Desktop (the bundled Mattermost needs it).`
2. **Switch server answers /health**: `SWITCH_SERVER` is set and `GET /health` returns 200. The fix text
   distinguishes three cases: the variable is unset; a 401 ("right host, wrong path: use the server address,
   not the Gateway"); and an HTML response ("that's the Gateway").
3. **Four agent keys are in .env**: fix `Run make register.`
4. **Room id is set**: `SWITCH_ROOM_ID`.
5. **people.yaml has no placeholders**: `identity.placeholders()` is empty.
6. **carbon_room.yaml is present**: fix `Pull main; P2 owns config/carbon_room.yaml.`
7. **Database initialises**: the subprocess `$(PY) -m carbon_room init` exits 0. Never import the ledger.
8. **Replay cache covers every seed file**:
   - Only when `llm.mode == "replay"`. Otherwise it passes with the detail `not needed (mode=<m>)`.
   - Every non-JSON file under `data/seed/*/` must have `data/cache/extractions/<sha256>.json`.
9. **API key present (live mode only)**.

**Reset.** `python -m carbon_room.room.reset [--yes] [--local-only]`.
1. Unless `--yes`, prompt `This deletes var/, out/ and data/inbox/ and archives the room. Type reset to
   continue: `. Any other answer prints `Cancelled.`, deletes nothing and exits 1.
2. `reset_local(repo_root)` removes `var/` and `out/` and the contents of `data/inbox/`, keeping `.gitkeep`. It
   never touches anything outside `repo_root`, and never touches `data/seed` or `data/demo_uploads`.
3. Re-initialise with `-m carbon_room init`.
4. Unless `--local-only`, call `reset_room` through carbon-room's `OpsClient` (S08), using M2's names:
   - `archive_room` on the old room
   - `create_room` named `emissions-reporting`
   - `invite_agent_to_room` for all four agents
   - write the new `SWITCH_ROOM_ID` to `.env`

**Tests:**
- One test per doctor check that fails with its fix text when broken on purpose (monkeypatched runner,
  `MockTransport`, tmp env and config), plus an all-green run.
- `test_reset_cancelled_deletes_nothing`.
- `test_reset_local_keeps_gitkeep_and_seed`.
- `test_reset_never_leaves_repo_root`.
- `test_reset_room_call_sequence`.
- `test_makefile_targets_exist_and_echo`: parse the Makefile; `make -n <target>` exits 0 for every target.

**Done when:**
- [ ] `make setup seed doctor test` works on a fresh clone.
- [ ] Each doctor check fails helpfully when broken.
- [ ] Two rehearsals back to back start from an identical state (manual, M5).

### S17 · README, setup docs and the needs-room test
**Stories:** 6.4, 1.1 (documentation) · **Wave:** 5 · **Depends on:** S15, S16, M1, M2
**Read:** contracts §8 and §10; story 6.4; `docs/setup-switch.md` (M1 notes); `docs/spikes.md`;
`data/seed/EXPECTED.md` (if present); the current `README.md`.
**Files:**
- Modify `README.md`, a full rewrite that keeps P1's sections where they fit.
- Modify `docs/setup-switch.md`.
- Create `tests/test_publish_needs_room.py` and `tests/room/test_readme.py`.

**README sections, in the story's order and with these exact `##` headings:**
1. `What it is`
2. `How Switch is used`. This covers the four agents on the direct protocol, the room setup, and *what breaks
   without Switch*, citing `tests/test_publish_needs_room.py`.
3. `Quick start`. Clone → `make setup seed register doctor run`, with expected times.
4. `Running the demo close`. Exact messages, and who types each.
5. `Traps and the rules that catch them`.
6. `What is synthetic and what is not claimed`.
7. `Spike results and fallbacks`.
8. `Architecture`. Link `Carbon Room Architecture.html`.
9. `Team and track`.

Numbers come from `EXPECTED.md` only. If it is missing, write "see `data/seed/EXPECTED.md`" and print no number.

**`tests/test_publish_needs_room.py`:**
- `python -m carbon_room --help` lists no `publish`, `resolve` or `approve` command.
- `core.ingest_file` with a human actor and no message id raises `NeedsRoomEvent`.
- `core.publish` with a human actor and `chat_message_id=""` raises `NeedsRoomEvent`. This test is skipped with
  reason "P2 publish not merged" while `NotImplementedError` is raised.
- No module outside `carbon_room/room` and `carbon_room/agents` calls `core.resolve(` or `core.publish(`.

**`tests/room/test_readme.py`:**
- The nine headings appear in order.
- Every `make <target>` mentioned exists in the Makefile.
- Every command line in "Running the demo close" that starts with `@` or `G-` parses with `grammar.parse` to the
  intent kind written next to it in an HTML comment, for example `<!-- close.start -->`.
- The README never contains the fake-only totals `22.9`, `29.2` or `13.2`.

**Done when:**
- [ ] A teammate who didn't write it follows it to a published close without asking a question. This is
  checked in M6.

### S18 · Real-core integration (when P2's core lands)
**Stories:** the real-core "Done when" of 4.5 and 5.2; feeds 7.1 · **Wave:** 5 · **Depends on:** P2's core on
`main`, `data/seed/EXPECTED.md`
**Read:** `data/seed/EXPECTED.md`; P2's `carbon_room/calc`, `carbon_room/checks` and `carbon_room/report` public
functions; `tests/fakes/fake_core.py`; plan §3.16.
**Files:**
- Create `tests/room/test_real_core_flow.py`.
- Modify `tests/fakes/fake_core.py` only to match the real core's option keys, labels, titles and gap order.
  The numbers stay fake.

**Behaviour:**
1. The test copies `config/`, `data/seed/` and `data/demo_uploads/` into `tmp_path`, `chdir`s there, and runs
   `handle_close_start` with `AsyncCore(carbon_room.core)` and `FakeRoom`.
2. It then plays the scripted resolutions in `EXPECTED.md` through `handle_gap_reply`:
   - the upload, by copying the demo upload into `data/inbox/`
   - `pick A`
   - approving the stale factor
   - approving the variance
3. It asserts the totals and coverage after each step against `EXPECTED.md`, the top-level post count of at most
   12, and the board.
4. It is skipped with a reason while `core.calculate` raises `NotImplementedError`.

Every mismatch found here is fixed in the room code (a new small PR) or raised with P2. The fake is updated to
mirror the real core's shapes.

**Done when:**
- [ ] Against the real core, the four scripted resolutions from `EXPECTED.md` move the total to the expected
  figure.

---

## 6. Manual tracks (not TDD; you, sometimes with an interactive Claude Code session)

### M1 · Switch, Mattermost and the room (story 1.1), now
Record every step, the version and the time taken in `docs/setup-switch.md` as you go.
- [ ] Open **Switch Console** and choose **Run a server on this computer**. Note the Console version, the server
  address it shows, and the first-start download time. Docker is already running; the bundled Mattermost needs
  it.
- [ ] `curl -s <server>/health` returns healthy. A 401 means the right host but the wrong path; an HTML page
  means you hit the Gateway.
- [ ] Put `SWITCH_SERVER=<server>` in `.env`.
- [ ] In the Gateway, create a **registration** API key on the API Keys page and put it in `.env` as
  `SWITCH_REGISTRATION_KEY`. If the Gateway offers no such key on a local server, note it. You will then
  register agents in Console and use `register --from-console`.
- [ ] Create the room `emissions-reporting`, and put its id in `.env` as `SWITCH_ROOM_ID`.
- [ ] A teammate follows `docs/setup-switch.md` on their own machine without asking you anything. This can wait
  until M6.

### M2 · Spikes S1–S6 and the route check (stories 1.3–1.8, 1.10), after M1 and S09
Run these in an interactive session. Spike scripts in `scripts/spikes/` are throwaway exploration, so TDD does
not apply. Record pass or fail, what you tried and the fallback in `docs/spikes.md`.
- [ ] Register the four agents (`python -m carbon_room.room.register`, or curl if S09 isn't merged yet), invite
  them, and set addressing to "Anyone".
- [ ] **S1 + S5** (`scripts/spikes/s1_threads.py`):
  - Save `GET /agents/{id}/ops` to `docs/switch-ops.json`.
  - Find `post_message`'s thread argument and the returned id.
  - Post a root and a threaded reply, and check in Mattermost that the reply is threaded.
  - Reply as a person in that thread, and check that the event's `thread_id` equals the root id.
  - Capture real frames (with keys removed) into `tests/room/fixtures/frames/captured_*.json`.
- [ ] **S2** (`scripts/spikes/s2_attachments.py`): attach a PDF, log the attachment fields, try the media routes
  (check Console's `download_attachment`, or the `sandbox-quantum/switch` source), and compare SHA-256. If it
  fails, `CARBON_ROOM_ATTACHMENTS=inbox`.
- [ ] **S3**: create users `lead` and `priya` in Mattermost, use two browser profiles, and record both sender ids.
- [ ] **S4** (`scripts/spikes/s4_four_sockets.py`): four sockets, a worker running `time.sleep(10)`, for 2 minutes
  with no `evicted`. If it fails, `CARBON_ROOM_SINGLE_AGENT=1`.
- [ ] **S6**: `create_room_document close-board` and update it. Is it visible in Mattermost, in Console, or in
  neither?
- [ ] **1.8**: put the summary table in `docs/spikes.md` and post it in the team chat; P1 and P2 acknowledge it.
- [ ] **1.10 route check**: can the direct client post a gap thread, receive the reply and call the core? If not,
  the fallback is Claude Code as the room agent, with `core` exposed over MCP. That would be a new spec set, so
  stop and re-plan.
- [ ] Then start the Opus session for S08 and the wave-2+ specs.

### M3 · `people.yaml` real ids (story 1.9), after S03 and M2-S3
- [ ] Fill in `switch_ids` and `username` for `lead` and `priya`. `make doctor` should show `✓ people.yaml has no
  placeholders`.

### M4 · Demo script (story 7.1), after S18 or once `EXPECTED.md` exists
- [ ] Write `docs/demo-script.md` with the beats and timings:
  - the mess (10 s)
  - the ledger builds (15 s)
  - the refusal with gap threads (30 s)
  - fixes in threads with the total moving (20 s)
  - the data-centre line (10 s)
  - the coverage slide (5 s)

  Give the exact messages and who types each. Numbers come only from `EXPECTED.md`. Add one judge-question
  answer per beat. Read aloud, it must fit in 90 s.

### M5 · Rehearsals (story 7.2)
- [ ] `make reset-demo`, then a full demo out loud, timed. Log the stumbles under "Notes" in the demo script.
  After Thursday, fix only demo-breakers.
- [ ] Two timed runs at or under 90 s, with every trap firing live.

### M6 · Clean-machine run (story 6.5), by Fri 12:00 PT
- [ ] Someone else follows the README on a machine or account that has never had this project. Log every snag
  in `docs/clean-machine-run.md`, and fix the README or scripts through small PRs.
- [ ] The run reaches "Published v1", and the log is committed.

### M7 · Video and fallback recording (story 7.3), by Fri 17:00 PT
- [ ] Record the demo video from a live run, plus an uncut screen recording of the room from the **same** run.
  End on `coverage.html`. Put the links in `docs/video.md`; keep the recordings outside the repo.

### M8 · Submit (story 7.4), by Sat 10:00 PT
- [ ] Make the repo public, tag `v1.0-submission`, and submit the video link, the README link and Track 01 (Best
  Business Workflow). Save the confirmation in the team chat.

---

## 7. Review focus

These are the five input classes most likely to bite a real user that no single story names. Each is pinned by
a test in the spec that owns the code.

1. **The same message arriving twice.** This happens across the four sockets, and again on replay after a
   reconnect. It must be handled exactly once, and the ignored copy must not shadow the accepted one. Pinned by
   S07 `test_events_delivered_in_order_and_duplicates_skipped` and S10 `test_duplicate_message_id_handled_once`
   and `test_ignored_copy_does_not_block_addressed_copy`.
2. **Mention formatting from Mattermost.** Capitals, `@name,` and `@name:`, backticks and extra spaces must
   still parse as the command. Pinned by the S02 table rows.
3. **Gap ids repeating per close.** `G-2 pick A` must resolve against the latest close only. Pinned by S13
   `test_fallback_in_channel_routes_and_replies_in_gap_thread`, with a second close in the fake.
4. **Hostile or odd attachment names and files.** Traversal, symlinks, unicode and oversize files must never
   escape `data/inbox/` or hand P1 a path it would reject. Pinned by the S11 `safe_name`, symlink and oversize
   tests.
5. **Display rounding of Decimal totals.** Half-up rounding, None, zero and large values must match the
   contract's "1 decimal tCO2e", and no float may ever appear. Pinned by S05 `test_t_rounding_half_up` and
   `test_t_handles_none_and_large`.

---

## 8. Story coverage map

| Story | Where |
|---|---|
| 1.1 | M1, S17 (docs) |
| 1.2 | S09 |
| 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.10 | M2 |
| 1.9 | S03 (template), M3 (real ids) |
| 2.1 | S07 |
| 2.2 | S06 |
| 2.3 | S08 |
| 2.4 | S10 |
| 2.5 | S15 |
| 2.6 | S11 |
| 3.1 | S02 |
| 3.2 | S03 |
| 3.3, 3.4 | S11 (+S13 handler) |
| 3.5 | S04 |
| 4.1, 4.2, 4.3, 4.4 | S12 |
| 4.5, 4.6 | S13 (fake), S18 (real) |
| 4.7, 4.8 | S14 |
| 5.1 | S05 |
| 5.2, 5.3 | S14 |
| 5.4 | S13 |
| 6.1, 6.2, 6.3 | S16 |
| 6.4 | S17 |
| 6.5 | M6 |
| 7.1 | M4 |
| 7.2 | M5 |
| 7.3 | M7 |
| 7.4 | M8 |
| 8.1 | S01 |
| 8.2 | S07 (server), S15 (loop test) |
