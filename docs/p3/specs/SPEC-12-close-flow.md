# SPEC-12 · Close flow: orchestrator and gap roots
Stories: P3-4.1, P3-4.2, P3-4.3, P3-4.4 · Branch: `p3-s12-close-flow` · PR title: "P3-S12 (4.1–4.4): close flow and gap roots"
Depends on (must be merged): SPEC-01, SPEC-05 · Wave: 3 · Estimated session time: 2 h

## 1. Goal
`@carbon-room close October` runs the visible close:
1. carbon-room posts the plan and hands collection to the collector.
2. The collector posts its (false) "all collected" statement.
3. carbon-room hands checking to the watchdog.
4. The watchdog opens one thread per gap, with a named owner.
5. carbon-room refuses a clean total and shows the verified and excluded figures.

The flow is a LangGraph `StateGraph`. The ledger, through core, is the only real state. Every number comes from
`summary()`.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.3, §3.9, §3.15 and §3.16
- `00-CONTRACTS.md` §4, §7 (phases, totals) and §10
- `carbon_room/config.py` (`load_sites`, `load_config`, `site`)
- `carbon_room/room/ports.py`, `carbon_room/room/messages.py` and `tests/fakes/fake_core.py`
- LangGraph 1.2: `from langgraph.graph import StateGraph, START, END`,
  `from langgraph.checkpoint.memory import MemorySaver` and
  `from langgraph.graph.state import CompiledStateGraph`. Async node functions work with `ainvoke`; a node may
  return `{}` (verified on the repo's venv).

## 3. Files
- Create `carbon_room/agents/orchestrator.py`
- Create `carbon_room/agents/gaps.py`
- Create `tests/room/test_orchestrator.py`
- Create `tests/room/test_gaps.py`

Don't edit `carbon_room/agents/__init__.py`, which P1 owns.

## 4. Public interface
```python
# gaps.py
def gap_number(gap_id: str) -> int                  # "G-12" → 12
async def post_new_gaps(ctx: Context, close_id: str, findings: list[Finding]) -> list[str]

# orchestrator.py
class CloseState(TypedDict):
    close_id: str
    month: str
    site_ids: list[str]
    site_names: list[str]
    factor_set: str
    findings: list[dict]                            # dataclasses.asdict(Finding) each

COLLECTOR: Actor = Actor("agent", "collector", "Collector")
async def load_close_config() -> tuple[list[str], list[str], str]   # (site_ids, site_names, factor_set)
def build_close_graph(ctx: Context) -> CompiledStateGraph
async def handle_close_start(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None
```

## 5. Behaviour
1. **`load_close_config()`** runs the config reads in a worker thread (`asyncio.to_thread`).
   - `site_ids` is the `id` of each `config.load_sites()["sites"]` entry, in file order.
   - `site_names` is `config.site(id).get("name") or id` for each.
   - `factor_set` is `config.load_config()["default_factor_set"]`.
   - `load_config` raising `FileNotFoundError` raises `ValueError("config/carbon_room.yaml is missing; P2 provides
     it")`.
   - `load_sites` raising `FileNotFoundError` raises `ValueError("config/sites.yaml is missing")`.
   - A config with no `default_factor_set` raises `ValueError("config/carbon_room.yaml has no
     default_factor_set")`.
2. **`handle_close_start`:**
   1. `month = intent.args["month"]`.
   2. `site_ids, site_names, factor_set = await load_close_config()`.
   3. `close_id = await ctx.core.start_close(month, site_ids, factor_set, actor, event.message_id)`.
   4. `ctx.room.begin_close(close_id)`.
   5. `await build_close_graph(ctx).ainvoke(state, {"configurable": {"thread_id": close_id}})`, where `state`
      holds those values and `findings: []`.
   6. Exceptions propagate to the caller, which is `app.on_error` in SPEC-15.
3. **Graph.** `StateGraph(CloseState)` with the nodes
   `plan → collect → calculate → check → post_gaps → summary → END` (and `START → plan`), compiled with
   `checkpointer=MemorySaver()`. The nodes are closures over `ctx`. Let `m = messages.month_label(state["month"])`.
   - **plan:** `await ctx.room.post("carbon-room", close_plan(m, close_id, site_names, factor_set))`.
   - **collect:**
     1. `await ctx.room.send_targeted("carbon-room", "collector", handoff_collect(m, site_names))`
     2. `report = await ctx.core.ingest(close_id, COLLECTOR)`
     3. `await ctx.room.post("collector", collector_statement(report))`
     4. `await ctx.on_phase_end(close_id)`
   - **calculate:** `await ctx.core.calculate(close_id)`, then `await ctx.on_phase_end(close_id)`.
   - **check:**
     1. `await ctx.room.send_targeted("carbon-room", "watchdog", handoff_check(m))`
     2. `findings = await ctx.core.check(close_id)`
     3. Return `{"findings": [dataclasses.asdict(f) for f in findings]}`.
   - **post_gaps:** rebuild the findings with `models.from_dict(Finding, d)`, then
     `await gaps.post_new_gaps(ctx, close_id, findings)`.
   - **summary:**
     1. `s = await ctx.core.summary(close_id)`
     2. `await ctx.room.post("carbon-room", summary_post(m, s, ctx.display))`
     3. `await ctx.on_phase_end(close_id)`
   - Every post in this flow is top level, with `essential=True`.
4. **LangGraph lever.** If checkpointing fights the async closures for more than 2 hours, replace the graph with
   the same node functions called in sequence. Keep `build_close_graph`'s signature: it returns any object with
   an `async ainvoke(state, config)`. Note the change in the PR's Deviations section. The tests don't depend on
   LangGraph internals, except `test_build_close_graph_has_nodes_in_order`, which is then deleted. That is
   recorded as a deviation, approved by this rule.
5. **`post_new_gaps(ctx, close_id, findings)`:**
   1. `_, open_gaps = await ctx.core.resume_state(close_id)`.
   2. `by_id = {f.finding_id: f for f in findings}`.
   3. For each gap sorted by `gap_number(gap.gap_id)` whose `thread_root_message_id is None`:
      1. `text = messages.gap_root(gap, by_id.get(gap.finding_id), ctx.display(gap.owner),
         fallback_hint=not ctx.threads)`
      2. `mid = await ctx.room.post("watchdog", text)`
      3. If `mid` is empty, log a WARNING `gap <id> root not posted` and skip it.
      4. Otherwise `await ctx.core.record_gap_thread(close_id, gap.gap_id, mid)`. If it raises `ValueError`,
         log an ERROR, leave the gap out of the result, and continue with the next gap.
      5. Append `gap.gap_id` to the result.
   4. Return the gap ids posted. A gap that already has a root is never posted.
6. **`gap_number("G-12")`** is `int(gap_id.split("-", 1)[1])`. A malformed id sorts last (it returns
   `10**9`).
7. **No computing.** Nothing here computes a figure, a status or a coverage. It doesn't import `carbon_room.ledger`
   or `carbon_room.core`; it calls `ctx.core`.

## 6. Test plan
Tests use the `ctx`, `fake_core`, `fake_room` and `people_config` fixtures (SPEC-01), with
`config.load_sites()` reading the repo's `sites.yaml` copy. They build events with the helper
`make_event(body, *, message_id="h-1", thread_id=None, sender="@switch-user-lead:test", sender_name="lead",
attachments=(), addressed=True, receiving_agent="carbon-room")`, defined in each test module. The actor is
`LEAD = Actor("human", "lead", "Sustainability Lead", "lead")`, and the intent is `Intent("close.start",
{"month": "2026-10"}, "carbon-room")`. Phase-end calls are recorded with
`ctx.on_phase_end = rec` (an async function appending `close_id` to a list). `run_close(ctx)` awaits
`handle_close_start(ctx, make_event("@carbon-room close October"), INTENT, LEAD)`.

**`tests/room/test_orchestrator.py`**

| Test | Act | Assert |
|---|---|---|
| `test_close_october_posts_plan_statement_roots_summary_in_order` | `run_close` | `[p.agent for p in fake_room.top_level()] == ["carbon-room", "collector", "watchdog", "watchdog", "watchdog", "watchdog", "carbon-room"]`; the texts are exactly `close_plan("October 2026", "2026-10-v1", ["HQ", "Warehouse-2", "Data Centre EU-West"], "FS-2026-10")`, `"All 5 October sources collected."`, the four `gap_root(...)` texts for G-1…G-4 (built from `fake_core` with display `"@<id>"`), and `summary_post("October 2026", fake_core.summary("2026-10-v1"), ctx.display)`; every post has `essential is True` [3, 5] |
| `test_handoffs_are_targeted` | `run_close` | `fake_room.targeted == [("carbon-room", "collector", "Collect October 2026 for HQ, Warehouse-2, Data Centre EU-West."), ("carbon-room", "watchdog", "Check October 2026: every rule, every claim.")]` [3] |
| `test_three_agent_names_post` | `run_close` | `{p.agent for p in fake_room.posts} == {"carbon-room", "collector", "watchdog"}` [3] |
| `test_start_close_gets_event_message_id_and_actor` | `run_close` | the first entry of `fake_core.calls` is `("start_close", {"month": "2026-10", "sites": ["hq", "warehouse-2", "dc-eu-west"], "factor_set": "FS-2026-10", "actor": LEAD, "chat_message_id": "h-1"})` [2] |
| `test_ingest_uses_collector_actor` | `run_close` | the `ingest` call's `actor == Actor("agent", "collector", "Collector")` [3] |
| `test_core_call_order` | `run_close` | `[c[0] for c in fake_core.calls] == ["start_close", "ingest", "calculate", "check", "resume_state", "record_gap_thread", "record_gap_thread", "record_gap_thread", "record_gap_thread", "summary"]` [3, 5] |
| `test_begin_close_called` | `run_close` | `fake_room.closes == ["2026-10-v1"]` [2] |
| `test_summary_post_equals_summary_output` | `run_close` | the last top-level text `== summary_post("October 2026", fake_core.summary("2026-10-v1"), ctx.display)`, and it contains `"Verified: 0.0 tCO2e · Excluded (not verified): 29.2 tCO2e · Coverage: 0%"` [3] |
| `test_on_phase_end_called_after_collect_calculate_summary` | `run_close` with `rec` | `rec` calls `== ["2026-10-v1"] * 3`. The first happens after the collector post (check with an `on_phase_end` that records `len(fake_room.posts)`: the values are `[2, 2, 7]`) [3] |
| `test_missing_config_raises_value_error` | a tmp config dir with only `sites.yaml`, `CARBON_ROOM_CONFIG_DIR` set, caches cleared | `run_close` | `ValueError("config/carbon_room.yaml is missing; P2 provides it")`; `fake_core.calls == []`; no posts [1] |
| `test_missing_default_factor_set` | a tmp `carbon_room.yaml` of `factor_sets: {}` | `run_close` | `ValueError("config/carbon_room.yaml has no default_factor_set")` [1] |
| `test_core_error_propagates` | `fake_core.fail["check"] = ValueError("boom")` | `run_close` | raises `ValueError("boom")`; the plan and the collector statement were posted, but no gap roots [2] |
| `test_fallback_hint_when_threads_off` | `ctx.threads = False` | `run_close` | each of the 4 watchdog posts ends with ``"anywhere in the room."``, and G-2's contains ``"Or type `G-2 pick A` anywhere in the room."`` [5] |
| `test_build_close_graph_has_nodes_in_order` | — | `build_close_graph(ctx).get_graph().nodes` | contains `plan`, `collect`, `calculate`, `check`, `post_gaps` and `summary` [3] |
| `test_load_close_config` | `people_config` | `await load_close_config()` | `(["hq", "warehouse-2", "dc-eu-west"], ["HQ", "Warehouse-2", "Data Centre EU-West"], "FS-2026-10")` [1] |

**`tests/room/test_gaps.py`**

Arrange each test with `fake_core.start_close(...)`, `ingest`, `calculate`, then `findings = fake_core.check(cid)`.

| Test | Act | Assert |
|---|---|---|
| `test_gap_roots_recorded_in_core` | `await post_new_gaps(ctx, cid, findings)` | returns `["G-1", "G-2", "G-3", "G-4"]`; `fake_core.gap_for_thread("m-1").gap_id == "G-1"` … `"m-4"` → G-4 [5] |
| `test_post_new_gaps_twice_posts_once` | call it twice | the second call returns `[]`; `len(fake_room.posts) == 4` [5] |
| `test_roots_use_owner_display_and_evidence` | `ctx.display = lambda pid: {"priya": "@priya.k"}.get(pid, pid)`; call it | the first post's text `== gap_root(G1, findings[0], "@priya.k")` [5] |
| `test_new_gap_without_finding_posts_without_evidence` | call it once. Then set `fake_core.on_resolve_open` to SPEC-01's R7 FINANCE finding and run `fake_core.resolve("G-4", "approve", LEAD, "h-2", {})`. Call it again with `findings=[]` | returns `["G-5"]`; that post has no `"Evidence:"` line [5] |
| `test_empty_message_id_is_not_recorded` | `ctx.room` is a `FakeRoom` subclass whose `post` returns `""` | call it | returns `[]`; no `record_gap_thread` call; a WARNING `gap G-1 root not posted` [5] |
| `test_record_error_is_logged_and_continues` | `fake_core.fail["record_gap_thread"] = ValueError("taken")` | call it | returns `["G-2", "G-3", "G-4"]` (G-1 failed to record and is not listed); an ERROR log [5] |
| `test_gap_number` | — | `gap_number("G-12")`, `gap_number("G-2")`, `gap_number("bad")` | `12`, `2`, `10**9` [6] |

## 7. Fixtures and doubles
`FakeCore`, `FakeRoom`, the `ctx` fixture and `people_config` (SPEC-01). No new fixture files.

## 8. Manual check
After SPEC-15 and with the real core (S18): `@carbon-room close October` in `october-close`. You should see the
plan, the collector's line, one thread per gap with the owner mentioned, and the refusal with figures. There are
three agent names.

## 9. Done when
- [ ] Against the fake core, `close October` posts the plan, the collector statement, the gap roots and a
      summary, in that order
- [ ] Three agent names post
- [ ] Each root is posted once
- [ ] The summary's numbers equal `summary()`
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/agents tests/room` (only the files this spec creates in `carbon_room/agents`)
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Thread replies and resolution (SPEC-13), and resume, budgets, noise and the board (SPEC-14).
- The real `on_phase_end` hook (`hooks.after_phase`, SPEC-14). Wiring (SPEC-15).

## 11. Open questions
None block execution. P2 questions 2 and 3 (plan §1.4) don't change this code: it posts whatever gaps
`resume_state` returns.
