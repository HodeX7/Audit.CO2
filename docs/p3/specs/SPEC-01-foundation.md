# SPEC-01 · Foundation: ports, AsyncCore, frames, fake core, fake room
Stories: P3-8.1, plus scaffolding · Branch: `p3-s01-foundation` · PR title: "P3-S01 (8.1): foundation, fake core and fake room"
Depends on (must be merged): none · Wave: 0 · Estimated session time: 1.5 h

> **Contract change (plan §3, edited in the same change as this spec)**
> 1. **§3.2 `frame_kind` order.** The Switch docs show the domain envelope only for `message`
>    (`{"event": "message", "data": {"type": "message", …}}`). They don't say whether a `command` frame has
>    `"event": "message"` or `"event": "command"`. A domain kind in `data.type` therefore wins over `event`.
>    The full order is in rule 1 below.
> 2. **§3.16 test hooks.** Two hooks are added: `keep_open: set[str]` and `audit: AuditCheck | None`.
>    SPEC-13 and SPEC-14 need a gap that stays open after `resolve`, and a broken audit chain.
> 3. **FakeRoom.link** returns `"message m-3"`, not `"(message m-3)"`. Templates put links inside their own
>    brackets, and the double brackets read badly. This matches `SwitchRoom.link` with no permalink base
>    (SPEC-15).

## 1. Goal
This spec creates the base that every other P3 spec builds on:
- the frame helpers (`room/frames.py`)
- the `Room` port and `Context` (`room/ports.py`)
- `AsyncCore`, which runs the synchronous core on a thread pool (`room/async_core.py`)
- the two test doubles, `FakeCore` (the contracts §10 story with fake numbers) and `FakeRoom`

After this, room code can be written and tested without Switch and without P2's core.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.2, §3.3, §3.4 and §3.16
- `00-CONTRACTS.md` §2 (types and exceptions), §4 (core API) and §10 (seed scenario)
- `carbon_room/core.py`, `carbon_room/models.py`, `carbon_room/config.py`
- `tests/test_core_signatures.py`, `tests/test_no_literals.py`, `tests/conftest.py`

## 3. Files
**Create**
- `carbon_room/room/frames.py`
- `carbon_room/room/ports.py`
- `carbon_room/room/async_core.py`
- `tests/fakes/fake_core.py`
- `tests/fakes/fake_room.py`
- `tests/room/conftest.py`
- `tests/room/fixtures/people.yaml`
- `tests/room/fixtures/carbon_room.yaml`
- `tests/room/test_fake_core.py`
- `tests/room/test_foundation.py`
- `tests/room/test_boundaries.py`
- `docs/switch-protocol-notes.md` (skeleton, §7)
- `docs/spikes.md` (skeleton, §7)

Don't create an `__init__.py` under `tests/`, and don't change any other file.

## 4. Public interface

### 4.1 `carbon_room/room/frames.py`
```python
DOMAIN_KINDS: frozenset[str] = frozenset({"message", "command", "room_join"})
CONTROL_KINDS: frozenset[str] = frozenset({"connection_state", "gap", "evicted", "subscription_changed",
                                           "room_released", "ping", "refused"})
def frame_kind(frame: object) -> str | None
def frame_fields(frame: object) -> dict
def sequence_of(frame: object) -> int | None
def pong(cursor: int) -> str
```

### 4.2 `carbon_room/room/ports.py`
```python
AGENT_NAMES: tuple[str, ...] = ("carbon-room", "collector", "watchdog", "reporter")
AGENT_TITLES: dict[str, str] = {"carbon-room": "Carbon Room", "collector": "Collector",
                                "watchdog": "Watchdog", "reporter": "Reporter"}

@runtime_checkable
class Room(Protocol):
    async def post(self, agent: str, text: str, *, thread_id: str | None = None,
                   essential: bool = True) -> str: ...
    async def send_targeted(self, from_agent: str, to_agent: str, text: str) -> None: ...
    async def upsert_doc(self, agent: str, name: str, content: str) -> bool: ...
    def link(self, message_id: str) -> str: ...
    def begin_close(self, close_id: str) -> None: ...

async def noop_phase_end(close_id: str) -> None

def utc_today() -> date                                   # datetime.now(timezone.utc).date()

@dataclass
class Context:
    core: Any
    room: Room
    display: Callable[[str], str] = str
    today: Callable[[], date] = utc_today
    on_phase_end: Callable[[str], Awaitable[None]] = noop_phase_end
    threads: bool = True
    attachments_mode: str = "inbox"
    inbox_dir: Path = Path("data/inbox")
    download: Callable[[Any], Awaitable[bytes]] | None = None
    out_dir: Path = Path("out")
    state: dict = field(default_factory=dict)
```

### 4.3 `carbon_room/room/async_core.py`
```python
CORE_FUNCTIONS: tuple[str, ...] = ("start_close", "ingest", "ingest_file", "calculate", "check", "resolve",
    "summary", "draft_report", "publish", "trace", "verify_audit", "resume_state", "latest_close",
    "gap_for_thread", "record_gap_thread", "budget_usage", "explain")

class AsyncCore:
    def __init__(self, core: Any, executor: concurrent.futures.Executor | None = None) -> None
    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]
```

### 4.4 `tests/fakes/fake_core.py`
```python
class FakeCore:
    def __init__(self, *, delay: float = 0.0) -> None
    # test hooks (public attributes)
    calls: list[tuple[str, dict]]          # (function name, bound arguments) for every call, in order
    delay: float                           # every method sleeps this many seconds first
    fail: dict[str, BaseException]         # the named method raises this once, then the entry is removed
    on_resolve_open: list[Finding]         # the next resolve() opens these as new gaps, then clears the list
    keep_open: set[str]                    # gap ids that resolve() leaves OPEN with no effect
    budget: dict                           # returned by budget_usage(); default {}
    audit: AuditCheck | None               # when set, verify_audit() returns it
    # every function in CORE_FUNCTIONS, with exactly core's parameter names and defaults, e.g.
    def start_close(self, month, sites, factor_set, actor, chat_message_id): ...
    def ingest_file(self, close_id, path, actor, chat_message_id, site=None): ...
    def resolve(self, gap_id, action, actor, chat_message_id, payload): ...
```

### 4.5 `tests/fakes/fake_room.py`
```python
@dataclass
class Post:
    agent: str; text: str; thread_id: str | None; essential: bool; message_id: str

class FakeRoom:                      # satisfies ports.Room
    def __init__(self, *, supports_docs: bool = True) -> None
    posts: list[Post]
    targeted: list[tuple[str, str, str]]       # (from_agent, to_agent, text)
    docs: dict[str, str]                       # name → content
    supports_docs: bool
    closes: list[str]                          # close ids passed to begin_close, in order
    async def post(self, agent, text, *, thread_id=None, essential=True) -> str
    async def send_targeted(self, from_agent, to_agent, text) -> None
    async def upsert_doc(self, agent, name, content) -> bool
    def link(self, message_id: str) -> str
    def begin_close(self, close_id: str) -> None
    def top_level(self) -> list[Post]
    def in_thread(self, thread_id: str) -> list[Post]
```

### 4.6 Fixtures in `tests/room/conftest.py`
| Fixture | Returns |
|---|---|
| `people_config` | the tmp config `Path`. It copies the repo's `config/sites.yaml`, `tests/room/fixtures/people.yaml` and `tests/room/fixtures/carbon_room.yaml` into `tmp_path / "config"`, sets `CARBON_ROOM_CONFIG_DIR` with `monkeypatch`, and calls `config.clear_caches()` before yielding and after |
| `fake_core` | `FakeCore()` |
| `fake_room` | `FakeRoom()` |
| `core_executor` | a `ThreadPoolExecutor(max_workers=4, thread_name_prefix="core")`, shut down at teardown with `wait=True` |
| `ctx` | `Context(core=AsyncCore(fake_core, core_executor), room=fake_room, display=lambda pid: f"@{pid}", today=lambda: date(2026, 11, 5))` |

`ctx` doesn't depend on `people_config`. Tests that need config request both.

## 5. Behaviour

### frames.py
1. **`frame_kind(frame)`**, applied in this order:
   1. Not a dict: return None.
   2. `frame["data"]` is a dict and `frame["data"].get("type")` is in `DOMAIN_KINDS`: return that value.
   3. Otherwise, for key in `("event", "type")`: if `frame.get(key)` is a str in `DOMAIN_KINDS | CONTROL_KINDS`,
      return it.
   4. Otherwise, if `frame["data"]` is a dict and its `type` is in `CONTROL_KINDS`, return it.
   5. Otherwise return None.
2. **`frame_fields(frame)`.**
   - Not a dict: `{}`.
   - `frame["data"]` is a dict: return that dict, the same object.
   - Otherwise: a new dict with every key except `"event"`, `"type"` and any key starting with `_`.
3. **`sequence_of(frame)`.**
   - Not a dict: None.
   - `frame["id"]` is an int and not a bool: return it.
   - `frame["id"]` is a str of ASCII digits: return `int` of it.
   - Otherwise, apply the same two tests to `frame["data"]["sequence"]` when `data` is a dict.
   - Otherwise return None.
4. **`pong(cursor)`** returns `json.dumps({"type": "pong", "cursor": cursor})`.

### ports.py
5. `Room` is a `typing.Protocol` decorated with `@runtime_checkable`.
6. `noop_phase_end` returns None and does nothing.
7. `Context()` defaults are exactly as in §4.2. `utc_today()` returns `datetime.now(timezone.utc).date()`.

### async_core.py
8. **Construction.** `__init__` stores `core` and the executor in ordinary attributes, so `__getattr__` only runs
   for missing names. With `executor=None`, it creates `ThreadPoolExecutor(max_workers=4,
   thread_name_prefix="core")`.
9. **Allowed names.** `__getattr__(name)` raises `AttributeError(name)` unless `name` is in `CORE_FUNCTIONS`. This
   happens at attribute access, before any call.
10. **Calls.** For an allowed name it returns an `async def` wrapper. Awaiting `wrapper(*args, **kwargs)` runs
    `getattr(core, name)(*args, **kwargs)` through
    `asyncio.get_running_loop().run_in_executor(executor, functools.partial(...))`.
11. **Errors.** Exceptions raised by the core propagate unchanged: same type, same object.

### FakeCore (the contracts §10 story with fake numbers)
12. **Close ids and state.**
    - `start_close(month, …)` returns `f"{month}-v{n}"`, where `n` counts closes already made for that month,
      plus one.
    - Each close has its own independent state: phase, gaps, lines and draft.
    - `latest_close()` returns the most recently created close id, or None.
    - Every function that takes a `close_id` raises `NotFound(f"unknown close: {close_id}")` for an unknown one.
13. **Every method, in this order:**
    1. Append `(name, bound_arguments)` to `calls`, where `bound_arguments` is
       `inspect.signature(...).bind(...).arguments` as a plain dict, with defaults applied.
    2. `time.sleep(self.delay)` if `delay > 0`.
    3. If `name in self.fail`, raise `self.fail.pop(name)`.
    4. Run the body while holding one `threading.RLock`.
    5. Return deep copies of any `Gap`, `Finding`, `CloseSummary` or `Report`, so callers can't change the fake's
       state.
14. **Phases.**
    - `start_close` → OPEN
    - `ingest` → COLLECTING
    - `calculate` → CALCULATING
    - `check` → AWAITING_HUMANS if any gap is open, else CHECKING
    - `resolve` → AWAITING_HUMANS if any gap is open after it, else CHECKING
    - `draft_report` → DRAFTED
    - `publish` → PUBLISHED
15. **`start_close(month, sites, factor_set, actor, chat_message_id)`.**
    - Raises `NeedsRoomEvent("human actions need a chat message id")` when `actor.kind == "human"` and
      `chat_message_id` is empty.
    - Accepts any month, sites and factor set.
16. **`ingest(close_id, actor)`.**
    - Creates the five lines in §7.2, all in state `excluded`.
    - Returns `IngestReport(close_id, 9, ["CL-0001", …, "CL-0009"], [], f"All 5 {Month} sources collected.")`,
      where `{Month}` is the English month name of the close's month, for example `October`.
17. **`ingest_file(close_id, path, actor, chat_message_id, site=None)`** raises `NeedsRoomEvent` for a human
    actor with an empty message id. Otherwise it returns `["CL-0010"]` and changes nothing.
18. **`calculate(close_id)`** sets the phase and returns `[]`.
19. **`check(close_id)`.**
    - The first call opens G-1…G-4 exactly as in §7.1, with `thread_root_message_id=None`,
      `opened_at="2026-11-06T16:00:00Z"`, and `resolved_*` and `resolution` None.
    - Later calls open nothing new.
    - It returns the findings of every OPEN gap in gap-number order, followed by the R6 finding (§7.1). It never
      opens a gap for R6.
20. **`resolve(gap_id, action, actor, chat_message_id, payload)`** always works on the **latest** close. Checks run
    in this order:
    1. A human actor with an empty `chat_message_id` raises `NeedsRoomEvent("human actions need a chat message
       id")`.
    2. An unknown gap in the latest close raises `NotFound(f"unknown gap: {gap_id}")`.
    3. If `actor.role is None`, or the actor is neither `role == "lead"` nor `actor.id == gap.owner`, it raises
       `NotAllowed(f"only the lead or the gap owner can resolve {gap_id}")`.
    4. A RESOLVED gap raises `ValueError(f"gap {gap_id} is already resolved")`.
    5. If `action` isn't the action of one of the gap's options, it raises
       `ValueError(f"gap {gap_id} has no {action} option")`.
    6. `action == "upload"` without a non-empty `payload.get("path")` raises
       `ValueError("upload needs payload['path']")`.
    7. If `gap_id in keep_open`, nothing changes.
    8. Otherwise the action is applied per §7.3. The gap gets `status="RESOLVED"`, `resolved_by=actor.id`,
       `resolved_message_id=chat_message_id` and `resolution={"action": action, "payload": dict(payload)}`.
    9. Each finding in `on_resolve_open` opens a new gap (the next free G-number, same fields as rule 19), and
       the list is cleared.
    10. The phase is set (rule 14), and the call returns the same list `check` would return now.
21. **`summary(close_id)`** returns `CloseSummary` with:
    - `close_id` and the current `phase`
    - `verified_kgco2e`: the sum of `verified` lines
    - `excluded_kgco2e`: the sum of `excluded` lines
    - `coverage_pct`: `(verified * 100 / (verified + excluded)).quantize(Decimal("1"), ROUND_HALF_UP)`, or
      `Decimal("0")` when both sums are 0
    - `sources_expected=4`
    - `sources_verified`: how many of `wh2-elec`, `hq-diesel`, `dc` and `hq-elec` (§7.2 "source") have a
      verified line
    - `open_gaps`: OPEN gaps sorted by gap number
    - `dc_line`: the `DcLine` in §7.1
    All numbers are `Decimal`.
22. **`draft_report(close_id)`.**
    - Sets DRAFTED and stores the s_tags (rule 23) as the close's draft.
    - Returns `Report(close_id, 1, verified/1000, excluded/1000, coverage, f"{sv} of 4 expected sources verified",
      gaps, conflicts, ["DEFRA 2026", "EGRID 2024", "EMBER 2025"], dc_line, s_tags,
      ["Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero"], None, None)`.
    - `gaps` is `[{"gap_id", "title", "owner"} …]` for each open gap in order. `conflicts` is
      `[{"gap_id": "G-2", "title": …, "owner": "lead"}]` while G-2 is open, else `[]`.
23. **s_tags.**
    - One `SourceTag` per `verified` line, in the §7.2 line order.
    - Tags are numbered `S-001`, `S-002`, …
    - The fields come from §7.2, with `page=1` and `status="VERIFIED"`.
    - `approver` and `chat_message_id` are the `actor.id` and message id of the `resolve` that verified the line.
24. **`publish(close_id, actor, chat_message_id)`.**
    - A human actor with an empty message id raises `NeedsRoomEvent`.
    - If `actor.role != "lead"`, it raises `NotAllowed("only the lead can publish")`.
    - If the phase isn't DRAFTED, it raises `ValueError("draft the report before publishing")`.
    - Otherwise it sets PUBLISHED and returns the stored draft's `Report` with `approver=actor.id` and
      `published_at="2026-11-06T17:00:00Z"`. It writes no files.
25. **`trace(close_id, tag)`** returns the stored draft's `SourceTag` with that tag. A missing tag, or no draft,
    raises `NotFound(f"unknown tag: {tag}")`.
26. **`verify_audit(close_id)`** returns `self.audit` when it is set. Otherwise it returns
    `AuditCheck(True, len(self.calls), None)`, where `calls` already includes this call.
27. **`resume_state(close_id)`** returns `(phase, open gaps sorted by gap number)`.
28. **`gap_for_thread(thread_root_message_id)`** searches every close and returns the gap, OPEN or RESOLVED,
    whose `thread_root_message_id` matches. Otherwise it returns None.
29. **`record_gap_thread(close_id, gap_id, message_id)`.**
    - An unknown gap raises `NotFound(f"unknown gap: {gap_id}")`.
    - An empty `message_id` raises `ValueError("gap thread message_id is required")`.
    - If the gap already has a root, nothing happens.
    - If any other gap, in any close, has that root, it raises
      `ValueError(f"Switch thread {message_id!r} is already linked to gap {other_gap_id}")`.
    - Otherwise the root is set.
30. **`budget_usage(close_id)`** returns `self.budget`.
31. **`explain(close_id, question, actor)`.**
    - Let `q = question.lower()`. The site is the first entry of §7.4 whose id or lowercased name occurs in `q`,
      else None.
    - The verified lines are those for that site, or for every site when the site is None.
    - With none, it returns `f"UNKNOWN for {site or 'this close'}, because no VERIFIED ledger rows match, owned by
      {owner}"`, where `owner` is the site's owner from §7.4, or `lead` when there is no site.
    - Otherwise it returns `"Verified ledger facts: "` + `"; ".join(f"{claim}: {site} {value} {unit}, {kg} kgCO2e,
      status VERIFIED")`, over those lines in line order.

### FakeRoom
32. **`post`.**
    - Appends `Post(agent, text, thread_id, essential, f"m-{n}")`, where `n` is `len(posts) + 1`.
    - Returns the id. Ids are `m-1`, `m-2`, … across all posts, top-level and threaded.
33. **`send_targeted`** appends to `targeted`.
34. **`upsert_doc`** returns False and stores nothing when `supports_docs` is False. Otherwise it sets
    `docs[name] = content` and returns True.
35. **`link(message_id)`** returns `f"message {message_id}"`.
36. **`begin_close`** appends to `closes`.
37. **Queries.** `top_level()` returns posts whose `thread_id is None`. `in_thread(t)` returns posts whose
    `thread_id == t`. Both keep post order.

## 6. Test plan
`fc` is a fresh `FakeCore()`. `LEAD = Actor("human", "lead", "Sustainability Lead", "lead")`,
`PRIYA = Actor("human", "priya", "Priya", "site_manager")` and
`GUEST = Actor("human", "guest:x", "x", None)`. The helper `run_to_check(fc)` does `cid = fc.start_close("2026-10",
["hq", "warehouse-2", "dc-eu-west"], "FS-2026-10", LEAD, "h-1")`, then `ingest(cid, Actor("agent", "collector",
"Collector"))`, `calculate(cid)` and `check(cid)`, and returns `cid`. The helper is defined in
`test_fake_core.py`, not in conftest.

**`tests/room/test_fake_core.py`**

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_fake_core_signatures_match_core` | — | for each name in `CORE_FUNCTIONS`, compare `inspect.signature(getattr(FakeCore, name))` (dropping `self`) with `inspect.signature(getattr(core, name))` | same parameter names in order, and the same `.default` for each [13] |
| `test_fake_core_has_every_core_function` | — | — | `set(CORE_FUNCTIONS) == {n for n, f in vars(core).items() if inspect.isfunction(f) and f.__module__ == core.__name__ and not n.startswith("_")}`, and every name is callable on `FakeCore` [13] |
| `test_start_close_ids_per_month` | `fc` | start 2026-10 twice and 2026-09 once | `"2026-10-v1"`, `"2026-10-v2"`, `"2026-09-v1"`; `latest_close() == "2026-09-v1"` [12, 15] |
| `test_ingest_report` | after `start_close` | `ingest` | `IngestReport(cid, 9, ["CL-0001", "CL-0002", "CL-0003", "CL-0004", "CL-0005", "CL-0006", "CL-0007", "CL-0008", "CL-0009"], [], "All 5 October sources collected.")`; phase COLLECTING [16] |
| `test_fake_scenario_after_check` | — | `run_to_check(fc)` | `resume_state` gives `AWAITING_HUMANS` and the gaps `[G-1, G-2, G-3, G-4]` with owners `[priya, lead, lead, lead]`, kinds `[PERIOD, CONFLICTING, STALE, VARIANCE]` and option keys `[["upload"], ["pick A", "pick B"], ["approve", "reject"], ["approve", "reject"]]`. `summary` has verified `Decimal("0")`, excluded `Decimal("29184")`, coverage `Decimal("0")`, sources 0 of 4 [14, 19, 21] |
| `test_check_returns_r6_but_opens_no_gap` | `run_to_check(fc)` | `fc.check(cid)` again | five findings: rules `["R4", "R2", "R3", "R5", "R6"]`; `resume_state` still has 4 gaps [19] |
| `test_fake_resolutions_follow_table` | `run_to_check(fc)` | in order: PRIYA `resolve("G-1", "upload", PRIYA, "h-2", {"path": "data/inbox/x.pdf", **G-1 params})`; LEAD `resolve("G-2", "pick", LEAD, "h-3", {"claim_id": "CL-0003"})`; LEAD `resolve("G-3", "approve", LEAD, "h-4", {"use_factor_id": "EMBER-2025-IE"})`; LEAD `resolve("G-4", "approve", LEAD, "h-5", {})` | after each, `(verified, excluded, coverage, sources_verified)` is `(3600, 25684, 12, 1)`, `(8920, 13980, 39, 2)`, `(13240, 9660, 58, 3)`, `(22900, 0, 100, 4)`; the final phase is `CHECKING` [20, 21] |
| `test_fake_resolution_order_independent` | `run_to_check(fc)` | G-4 approve, then G-2 pick A | verified `Decimal("14980")`, excluded `Decimal("7820")`, coverage `Decimal("66")` [21] |
| `test_reject_resolves_and_keeps_line_excluded` | `run_to_check(fc)` | LEAD `resolve("G-3", "reject", LEAD, "h-4", {"reason": "no"})` | G-3 is not in `resume_state`'s gaps; verified 0; excluded 29184 [20, §7.3] |
| `test_pick_b_keeps_b` | `run_to_check(fc)` | LEAD pick `{"claim_id": "CL-0002"}` on G-2 | verified `Decimal("6384")`, excluded `Decimal("17480")` [§7.3] |
| `test_fake_role_and_message_guards` | `run_to_check(fc)` | five calls | GUEST resolve G-2 raises `NotAllowed`; PRIYA resolve G-2 raises `NotAllowed`; LEAD resolve G-2 with `""` raises `NeedsRoomEvent`; PRIYA upload G-1 with `{}` raises `ValueError`; LEAD pick A twice on G-2 makes the second raise `ValueError("gap G-2 is already resolved")` (compare `str(exc)`) [20] |
| `test_resolve_unknown_gap_and_wrong_action` | `run_to_check(fc)` | resolve `"G-9"`; resolve G-2 with `"approve"` | `NotFound`; `ValueError("gap G-2 has no approve option")` [20] |
| `test_resolve_uses_latest_close` | `run_to_check(fc)` twice (v1, then v2) | LEAD pick A on G-2 | v2's G-2 is RESOLVED and v1's G-2 is still OPEN (via `resume_state("2026-10-v1")`) [20] |
| `test_publish_guards_and_draft_needed` | `run_to_check(fc)` | PRIYA publish; LEAD publish before draft; draft, then LEAD publish | `NotAllowed`; `ValueError("draft the report before publishing")`; a `Report` with `approver == "lead"`, `published_at == "2026-11-06T17:00:00Z"`, phase PUBLISHED [24] |
| `test_draft_report_shape` | all four resolutions done | `draft_report` | version 1; `verified_total_tCO2e == Decimal("22.9")`; `unverified_excluded_tCO2e == Decimal("0")`; `source_coverage == "4 of 4 expected sources verified"`; `gaps == []`; `conflicts == []`; tags `["S-001", "S-002", "S-003", "S-004"]` for claims `["CL-0004", "CL-0003", "CL-0001", "CL-0010"]`; `s_tags[0].approver == "lead"` and `chat_message_id == "h-5"`; `s_tags[3].approver == "priya"` [22, 23] |
| `test_draft_report_lists_open_gaps_and_conflict` | `run_to_check(fc)` | `draft_report` | `gaps[1] == {"gap_id": "G-2", "title": "HQ October diesel has two invoices 400 L apart", "owner": "lead"}`; `len(gaps) == 4`; `conflicts == [gaps[1]]`; `s_tags == []` [22] |
| `test_trace` | all four resolutions, then draft | `trace(cid, "S-001")`, `trace(cid, "S-099")` | the first has `file_name == "hq_electricity_2026-10.pdf"` and `kgco2e == Decimal("9660")`; the second raises `NotFound("unknown tag: S-099")` [25] |
| `test_fake_threads` | `run_to_check(fc)` | `record_gap_thread(cid, "G-2", "m-4")`; `gap_for_thread("m-4")`; `record_gap_thread(cid, "G-2", "m-9")`; `record_gap_thread(cid, "G-3", "m-4")`; `gap_for_thread("nope")` | G-2 is returned; the second call is a no-op (root still `m-4`); the third raises `ValueError`; the last returns None [28, 29] |
| `test_fake_explain_before_and_after_upload` | `run_to_check(fc)` | explain `"what is Warehouse-2 October electricity?"` before and after the G-1 upload | `"UNKNOWN for warehouse-2, because no VERIFIED ledger rows match, owned by priya"`, then `"Verified ledger facts: CL-0010: warehouse-2 18000 kWh, 3600 kgCO2e, status VERIFIED"` [31] |
| `test_explain_without_site` | `run_to_check(fc)` | explain `"why is this open?"` | `"UNKNOWN for this close, because no VERIFIED ledger rows match, owned by lead"` [31] |
| `test_hooks_fail_once_delay_keep_open_audit_budget` | `run_to_check(fc)` | set `fail["summary"] = NotFound("x")`, then call `summary` twice; set `keep_open = {"G-2"}`, then pick A on G-2; set `audit = AuditCheck(False, 7, 3)`; set `budget = {"collector": {"used": 9, "limit": 10, "state": "warn"}}` | the first summary raises, the second works; G-2 stays OPEN and verified stays 0; `verify_audit(cid) == AuditCheck(False, 7, 3)`; `budget_usage(cid)` returns the dict [13, 20, 26, 30] |
| `test_on_resolve_open_adds_gap` | `run_to_check(fc)`; `on_resolve_open = [Finding("F-0000000007", "R7", "FINANCE", ["CL-0004"], "hq", "2026-10", "finance", "HQ electricity needs finance sign-off", ["Amount: 9660"], [Option("approve", "approve", "Sign off")], 2, False)]` | LEAD approve G-4 | `resume_state` lists G-1, G-2, G-3 and G-5 (owner finance, no root); `on_resolve_open == []`; the returned findings include `F-0000000007` [20] |
| `test_delay_applies` | `FakeCore(delay=0.2)` | time `latest_close()` | it takes at least 0.2 s [13] |
| `test_calls_record_bound_arguments` | `fc` | `fc.ingest_file("c", "p", LEAD, "h")` | `fc.calls[-1] == ("ingest_file", {"close_id": "c", "path": "p", "actor": LEAD, "chat_message_id": "h", "site": None})` [13] |
| `test_returned_objects_are_copies` | `run_to_check(fc)` | change `resume_state(cid)[1][0].status` to `"RESOLVED"` | a fresh `resume_state` still shows it OPEN [13] |

**`tests/room/test_foundation.py`**

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_frames_kind_and_fields_both_envelopes` | the frames below | `frame_kind`, `frame_fields`, `sequence_of` | `{"type": "ping"}` gives ping, fields `{}`, seq None. `{"event": "message", "data": {"type": "message", "payload": {}, "sequence": 7}, "id": 7}` gives message, fields is the `data` dict, seq 7. `{"event": "evicted", "data": {"code": "heartbeat_lapsed"}}` gives evicted, fields `{"code": "heartbeat_lapsed"}`. `{"type": "connection_state", "generation": 3, "cursor": 10}` gives connection_state, fields `{"generation": 3, "cursor": 10}` [1–3] |
| `test_frames_domain_type_wins_over_event` | `{"event": "message", "data": {"type": "command", "sequence": 9}, "id": 9}` and `{"event": "room_join", "data": {"type": "room_join"}}` | `frame_kind` | `"command"` and `"room_join"` [1] |
| `test_frames_garbage` | `{}`, `{"type": "nope"}`, `{"event": 5}`, `{"data": "x"}`, `[]`, `None`, `"ping"` | all three functions | `frame_kind` gives None, `frame_fields` gives `{}` for non-dicts, `sequence_of` gives None [1–3] |
| `test_sequence_of_variants` | `{"id": "12"}`, `{"id": True}`, `{"data": {"sequence": 5}}`, `{"id": "x", "data": {"sequence": "6"}}` | `sequence_of` | 12, None, 5, 6 [3] |
| `test_frame_fields_drops_private_keys` | `{"_source": "docs", "type": "ping", "x": 1}` | `frame_fields` | `{"x": 1}` [2] |
| `test_pong_payload` | — | `pong(42)` | `json.loads(...) == {"type": "pong", "cursor": 42}` [4] |
| `test_context_defaults` | — | `Context(core=None, room=FakeRoom())` | `threads is True`, `attachments_mode == "inbox"`, `inbox_dir == Path("data/inbox")`, `out_dir == Path("out")`, `state == {}`, `display("x") == "x"`, `today() == datetime.now(timezone.utc).date()`, `asyncio.run(on_phase_end("c")) is None`, and two Contexts don't share `state` [6, 7] |
| `test_agent_names_and_titles` | — | — | `AGENT_NAMES == ("carbon-room", "collector", "watchdog", "reporter")`; `set(AGENT_TITLES) == set(AGENT_NAMES)` [§4.2] |
| `test_async_core_runs_in_worker_thread` | an object with `def latest_close(self): return threading.get_ident()` | inside `asyncio.run`, compare `await AsyncCore(obj).latest_close()` with `threading.get_ident()` | they differ, and the worker thread's name starts with `"core"` [8, 10] |
| `test_async_core_passes_args` | `fc` | `await AsyncCore(fc).ingest_file("c", "p", LEAD, "h", site="hq")` | `fc.calls[-1][1]["site"] == "hq"` [10] |
| `test_async_core_rejects_unknown_name` | — | `AsyncCore(object()).connect` | raises `AttributeError` [9] |
| `test_async_core_propagates_exceptions` | `fc.fail["summary"] = e = NotFound("x")` | `await AsyncCore(fc).summary("c")` | raises `NotFound`, and the raised object `is e` [11] |
| `test_async_core_uses_given_executor` | a `ThreadPoolExecutor(1, thread_name_prefix="given")` | await a call that records the thread name | the name starts with `"given"` [8] |
| `test_fake_room_ids_and_queries` | `FakeRoom()` | post top-level as carbon-room, then in thread `"m-1"` as watchdog, then top-level as reporter | ids `m-1`, `m-2`, `m-3`; `top_level()` agents `["carbon-room", "reporter"]`; `in_thread("m-1")` has one post with `essential is True`; `link("m-2") == "message m-2"` [32, 35, 37] |
| `test_fake_room_targeted_docs_closes` | `FakeRoom(supports_docs=False)` and `FakeRoom()` | `send_targeted`, `upsert_doc`, `begin_close` | `targeted == [("carbon-room", "collector", "hi")]`; False and `docs == {}` for the first; True and `{"close-board": "x"}` for the second; `closes == ["c-1"]` [33, 34, 36] |
| `test_fake_room_satisfies_room_protocol` | — | — | `isinstance(FakeRoom(), Room)` [5] |
| `test_people_config_fixture` | `people_config` | `config.load_people()`, `config.load_config()` | 4 people, the first with id `lead`; `load_config()["noise"]["max_top_level_posts"] == 12`; `os.environ["CARBON_ROOM_CONFIG_DIR"] == str(people_config)` [§4.6] |
| `test_ctx_fixture` | `ctx`, `fake_core` | `await ctx.core.latest_close()` | None; `ctx.display("priya") == "@priya"`; `ctx.today() == date(2026, 11, 5)` [§4.6] |

**`tests/room/test_boundaries.py`**

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_p3_code_never_imports_ledger` | files: `carbon_room/room/*.py`, plus whichever of `carbon_room/agents/{orchestrator,gaps,resolution,publish,reports,ask,notices,hooks}.py` exist | read each and search with `re.MULTILINE` | no match for `carbon_room\.ledger`, `from carbon_room import ledger`, or `^\s*(from\|import)\s+(tests\|fakes)\b` |
| `test_fakes_live_only_under_tests` | — | `Path("carbon_room").rglob("fake*.py")` | empty |

## 7. Fixtures and doubles

### 7.1 Gaps and findings (opened by the first `check`)
`<month>` is the close's month, for example `2026-10`. Findings have `tier=2`, and `blocking=True` except R6.

| Gap | finding_id | rule · kind | site | owner | claim_ids | title | evidence (exact, in order) | options `(key, action, label, params)` |
|---|---|---|---|---|---|---|---|---|
| G-1 | `F-0000000001` | R4 · PERIOD | warehouse-2 | priya | `["CL-0005"]` | `Warehouse-2 October bill is a September bill` | `File name: warehouse2_electricity_2026-10.pdf`; `Billing period: 1–30 Sep 2026` (en dash) | `("upload", "upload", "Upload the October bill", {"site": "warehouse-2", "month": <month>, "activity": "electricity_kwh"})` |
| G-2 | `F-0000000002` | R2 · CONFLICTING | hq | lead | `["CL-0003", "CL-0002"]` | `HQ October diesel has two invoices 400 L apart` | `Invoice 4471: Diesel delivered: 2000 L`; `Invoice 4471-rev: Diesel delivered: 2400 L` | `("pick A", "pick", "Invoice 4471 — 2,000 L", {"claim_id": "CL-0003"})`, `("pick B", "pick", "Invoice 4471-rev — 2,400 L", {"claim_id": "CL-0002"})` (em dashes) |
| G-3 | `F-0000000003` | R3 · STALE | dc-eu-west | lead | `["CL-0001"]` | `Data centre invoice uses last year's Ember factor` | `vendor_factor_ref: Ember 2024 IE`; `Locked factor set FS-2026-10 uses Ember 2025` | `("approve", "approve", "Use the locked Ember 2025 IE factor", {"use_factor_id": "EMBER-2025-IE"})`, `("reject", "reject", "Exclude the cloud line", {})` |
| G-4 | `F-0000000004` | R5 · VARIANCE | hq | lead | `["CL-0004"]` | `HQ October electricity is 38% above September` | `September: 35000 kWh`; `October: 48300 kWh (+38%)` | `("approve", "approve", "Accept +38% against September", {})`, `("reject", "reject", "Exclude HQ electricity", {})` |
| (none) | `F-0000000006` | R6 · DATACENTRE | dc-eu-west | lead | `["CL-0001"]` | `Data centre invoice has no per-model AI breakdown` | `ai_breakdown: none on the invoice` | none; `blocking=False` |

`DcLine(Decimal("4320"), Decimal("0"), Decimal("1.2"), "Market-based 0 relies on certificates; certificate quality
not verified", "UNVERIFIED", "No per-model AI breakdown on the invoice.")`

### 7.2 Lines (created by `ingest`; `wh2-oct` is added by the G-1 upload)
Every `sha256` is the 12-hex prefix shown, followed by `"0" * 52`.

| line | claim | source | site | activity | value | unit | kgCO2e | file_name | excerpt | sha prefix | factor_id | version | geography | recompute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hq-elec | CL-0004 | hq-elec | hq | electricity_kwh | 48300 | kWh | 9660 | `hq_electricity_2026-10.pdf` | `Total consumption: 48300 kWh` | `4c1d8e2a9b70` | `EGRID-2024-CAMX` | `2024` | `CAMX` | `48300 kWh × 0.2 kgCO2e/kWh = 9660 kgCO2e` |
| diesel-A | CL-0003 | hq-diesel | hq | diesel_l | 2000 | L | 5320 | `hq_diesel_2026-10_inv-4471.eml` | `Diesel delivered: 2000 L` | `3b7f0c5d1e92` | `DEFRA-2026-DIESEL` | `2026` | `UK` | `2000 L × 2.66 kgCO2e/L = 5320 kgCO2e` |
| diesel-B | CL-0002 | hq-diesel | hq | diesel_l | 2400 | L | 6384 | `hq_diesel_2026-10_inv-4471-rev.eml` | `Diesel delivered: 2400 L` | `2a6e9b4c0d81` | `DEFRA-2026-DIESEL` | `2026` | `UK` | `2400 L × 2.66 kgCO2e/L = 6384 kgCO2e` |
| wh2-sep | CL-0005 | wh2-elec | warehouse-2 | electricity_kwh | 17500 | kWh | 3500 | `warehouse2_electricity_2026-10.pdf` | `Billing period: 1–30 Sep 2026` | `5d2f7a1c8e63` | `DEFRA-2026-UK` | `2026` | `UK` | `17500 kWh × 0.2 kgCO2e/kWh = 3500 kgCO2e` |
| dc | CL-0001 | dc | dc-eu-west | dc_it_kwh | 14400 | kWh | 4320 | `dc_euwest_cloud_2026-10.json` | `it_energy_kwh: 14400` | `1e8c3f6a2b05` | `EMBER-2025-IE` | `2025` | `IE` | `14400 kWh × 0.3 kgCO2e/kWh = 4320 kgCO2e` |
| wh2-oct | CL-0010 | wh2-elec | warehouse-2 | electricity_kwh | 18000 | kWh | 3600 | `warehouse2_electricity_2026-10_actual.pdf` | `Billing period: 1–31 Oct 2026` | `6f4a0e3b9c27` | `DEFRA-2026-UK` | `2026` | `UK` | `18000 kWh × 0.2 kgCO2e/kWh = 3600 kgCO2e` |

All values are `Decimal`. Each line's state is `excluded`, `verified` or `dropped`. Only `excluded` and `verified`
lines count in a summary.

### 7.3 Effects of a resolved action
| Gap · action | Effect |
|---|---|
| G-1 `upload` | add `wh2-oct` as `verified`; `wh2-sep` becomes `dropped` |
| G-2 `pick` with `claim_id` CL-0003 | `diesel-A` becomes `verified`; `diesel-B` becomes `dropped` |
| G-2 `pick` with `claim_id` CL-0002 | `diesel-B` becomes `verified`; `diesel-A` becomes `dropped` |
| G-3 `approve` | `dc` becomes `verified` |
| G-4 `approve` | `hq-elec` becomes `verified` |
| any `reject` | no line changes; the gap still resolves |
| an `on_resolve_open` gap (any action) | no line changes |

### 7.4 Sites the fake knows (explain only)
`[("hq", "HQ", "lead"), ("warehouse-2", "Warehouse-2", "priya"), ("dc-eu-west", "Data Centre EU-West", "lead")]`
as (id, name, owner). The fake doesn't read config.

### 7.5 `tests/room/fixtures/people.yaml` (exact)
```yaml
people:
  - { id: lead,    name: "Sustainability Lead", role: lead,         username: lead,  switch_ids: ["@switch-user-lead:test"] }
  - { id: priya,   name: "Priya",               role: site_manager, username: priya, sites: [warehouse-2], switch_ids: ["@switch-user-priya:test"] }
  - { id: finance, name: "Finance Approver",    role: finance,      username: "",    switch_ids: [] }
  - { id: auditor, name: "External Auditor",    role: auditor,      username: "",    switch_ids: [] }
```

### 7.6 `tests/room/fixtures/carbon_room.yaml` (exact)
```yaml
factor_sets:
  FS-2026-10: { DEFRA: "2026", EGRID: "2024", EMBER: "2025" }
default_factor_set: FS-2026-10
budgets:
  default_tokens: 200000
  warn_at: 0.8
llm:
  mode: rules
noise:
  max_top_level_posts: 12
```

### 7.7 `docs/switch-protocol-notes.md` skeleton (exact)
```markdown
# Switch protocol notes

What the P3 room client actually uses, confirmed against a running server. Each section is owned by one spec and
edited only by it. Plan §1.5 has the documented facts; spikes are in docs/spikes.md.

## S06 events
_Not written yet._

## S07 connection
_Not written yet._

## S08 ops
_Not written yet._

## S09 register
_Not written yet._
```

### 7.8 `docs/spikes.md` skeleton (exact)
```markdown
# Spikes

Each spike records what was tried, what happened, pass or fail, and the fallback chosen (plan §6 M2).

| Spike | Question | Result | Fallback in use |
|---|---|---|---|
| S1 | Can an agent post into a thread? | not run | — |
| S2 | Can an agent download an attachment? | not run | — |
| S3 | Do two humans get distinct sender ids? | not run | — |
| S4 | Do four sockets stay up under a blocking worker? | not run | — |
| S5 | Does post_message return the new message id? | not run | — |
| S6 | Are room documents visible to people? | not run | — |

## S1 threads
_Not run._

## S2 attachments
_Not run._

## S3 two humans
_Not run._

## S4 four sockets
_Not run._

## S5 message ids
_Not run._

## S6 room documents
_Not run._
```

## 8. Manual check
None.

## 9. Done when
- [ ] `test_core_signatures` passes against the fake too (`test_fake_core_signatures_match_core`)
- [ ] The fake lives only under `tests/` (`test_fakes_live_only_under_tests`)
- [ ] Every test in §6 passes, and the full `.venv/bin/pytest -q` passes (the 41 existing tests included)
- [ ] `.venv/bin/ruff check carbon_room/room tests/room tests/fakes` passes
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`
      (`tests/test_no_literals.py` passes)

## 10. Not in this spec
- Event decoding (SPEC-06), the grammar (SPEC-02), templates (SPEC-05) and anything that posts.
- Mirroring P2's real option keys or gap order (SPEC-18).

## 11. Open questions
None block execution. P2's answers to plan §1.4 may change the fake later (SPEC-18). The numbers stay fake.
