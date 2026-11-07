# SPEC-14 · Room hygiene: resume, budget notices, noise guard, Close Board
Stories: P3-4.7, P3-4.8, P3-5.3, P3-5.2 · Branch: `p3-s14-hygiene` · PR title: "P3-S14 (4.7, 4.8, 5.3, 5.2): resume, notices, noise guard, board"
Depends on (must be merged): SPEC-12 (and so SPEC-01 and SPEC-05) · Wave: 3 · Estimated session time: 1.5 h

**Cut order (plan §4.2):** if time runs short, drop the board first (rules 9–10 and their tests), then the budget
notices (rules 5–6). Resume and the noise guard stay.

## 1. Goal
This spec keeps the room tidy and recoverable:
- **Resume.** After a crash or restart, carbon-room posts where the close stands and links the existing gap
  threads. It never reposts a root.
- **Budget notices.** Each agent gets one warning, and one stop notice, per close.
- **Noise guard.** The top level stays at or under 12 posts per close. Non-essential lines are merged into the
  next essential post.
- **Close Board.** A room document is kept in step with `summary()`.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.3, §3.9 and §3.16
- `00-CONTRACTS.md` §4 (`resume_state`, `budget_usage`) and §9 (`noise`, `budgets`)
- `carbon_room/agents/orchestrator.py` and `carbon_room/agents/gaps.py` (SPEC-12), and
  `carbon_room/room/messages.py` (SPEC-05)

## 3. Files
- Modify `carbon_room/agents/orchestrator.py`: add the three resume functions only, and change nothing else
- Create `carbon_room/agents/notices.py`, `carbon_room/agents/hooks.py`, `carbon_room/room/noise.py` and
  `carbon_room/room/board.py`
- Create `tests/room/test_resume.py`, `tests/room/test_notices.py`, `tests/room/test_noise.py` and
  `tests/room/test_board.py`

## 4. Public interface
```python
# orchestrator.py (added)
async def resume(ctx: Context, close_id: str) -> None
async def handle_resume(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None
async def resume_on_startup(ctx: Context) -> bool

# notices.py
async def warn_label() -> str                               # "80%" from config budgets.warn_at
async def check_budgets(ctx: Context, close_id: str) -> list[str]   # the notices posted

# hooks.py
async def after_phase(ctx: Context, close_id: str) -> None   # board, then budgets; never raises

# noise.py
class NoiseGuard:                                            # implements ports.Room
    def __init__(self, inner: Room, *, max_posts: int = 12, reserve: int = 2) -> None
    top_level_count: int
    buffered: list[str]
    async def post(self, agent, text, *, thread_id=None, essential=True) -> str
    async def send_targeted(self, from_agent, to_agent, text) -> None
    async def upsert_doc(self, agent, name, content) -> bool
    def link(self, message_id: str) -> str
    def begin_close(self, close_id: str) -> None
def max_posts_from_config() -> int                           # config noise.max_top_level_posts, default 12

# board.py
BOARD_NAME: str = "close-board"
async def update_board(ctx: Context, close_id: str) -> bool
```

## 5. Behaviour

### Resume
1. **`resume(ctx, close_id)`.**
   1. `phase, gaps = await core.resume_state(close_id)`.
   2. carbon-room posts `resume_line(month_label(month_of(close_id)), phase, gaps, ctx.display, ctx.room.link)` at
      top level, essential.
   3. `await gaps_module.post_new_gaps(ctx, close_id, [])`. This posts roots only for open gaps that have none,
      without evidence. It never reposts an existing root.
2. **`handle_resume`.**
   - `close_id = await core.latest_close()`. If it is None, carbon-room replies `no_close()` in the command
     thread (`event.thread_id or event.message_id`).
   - Otherwise `await resume(ctx, close_id)`. It does **not** call `begin_close`.
3. **`resume_on_startup(ctx)`.**
   - `close_id = await core.latest_close()`. If it is None, return False with no posts.
   - `phase, _ = await core.resume_state(close_id)`. If `phase == "PUBLISHED"`, return False.
   - Otherwise call `ctx.room.begin_close(close_id)` (it's a fresh process), then `await resume(ctx, close_id)`,
     and return True.

### Budget notices
4. **`warn_label()`.**
   - Read `config.load_config().get("budgets", {}).get("warn_at", 0.8)` in a worker thread.
   - Format it as `messages.pct(Decimal(str(value)) * 100)`, so 0.8 gives `"80%"`.
   - A missing config (`FileNotFoundError`) uses 0.8.
5. **`check_budgets(ctx, close_id)`.**
   1. `usage = await core.budget_usage(close_id)`.
   2. `sent = ctx.state.setdefault("budget_notices", set())`.
   3. For each agent in `sorted(usage)` whose `state` is `warn` or `stopped`: skip it when the key
      `(close_id, agent, state)` is in `sent`. Otherwise carbon-room posts `budget_warn(agent, await
      warn_label())` or `budget_stopped(agent)`, at top level with `essential=False`. Then add the key.
   4. Return the texts posted, in order.
   - The `ok` state and unknown states post nothing.
6. **One of each per close.** A `warn` and a later `stopped` for the same agent and close each post once.

### Noise guard
7. **`NoiseGuard`** wraps any `Room`.
   - **Thread posts** (`thread_id` set) pass straight to `inner.post` and are not counted.
   - **Non-essential top-level posts:** when `top_level_count >= max_posts - reserve`, append the text to
     `buffered`, log a WARNING `noise guard merged a post into the next one`, and return `""` without posting.
   - **Essential top-level posts:** when `buffered` is non-empty, the text becomes
     `"\n".join(buffered) + "\n\n" + text` and the buffer clears.
   - **Every top-level post that is sent** goes through `inner.post(agent, text, thread_id=None,
     essential=essential)`, and `top_level_count += 1`. When the count then exceeds `max_posts`, log a WARNING
     `top-level posts for this close: <n> (limit <max>)`. Essential posts are never held back.
   - **`begin_close`** resets the count and the buffer, then calls `inner.begin_close(close_id)`.
   - `send_targeted`, `upsert_doc` and `link` delegate to `inner` unchanged.
8. **`max_posts_from_config()`** returns `config.load_config().get("noise", {}).get("max_top_level_posts", 12)`
   as an int, or 12 when the config is missing. SPEC-15 calls it. The guard itself takes `max_posts` as an
   argument.

### Close Board
9. **`update_board(ctx, close_id)`.**
   1. `s = await core.summary(close_id)`.
   2. `ok = await ctx.room.upsert_doc("carbon-room", BOARD_NAME, board(month_label(month_of(close_id)), s,
      ctx.display, ctx.room.link))`.
   3. Return `ok`. When `ok` is False (spike S6 failed), there is no fallback post: the summary posts already carry
      the same figures, and the noise budget can't afford one.
10. **`after_phase(ctx, close_id)`** awaits `update_board`, then `check_budgets`. Each runs in its own
    `try/except Exception`, which logs at ERROR with `exc_info` and carries on. `after_phase` never raises. SPEC-15
    wires it as `ctx.on_phase_end`.

## 6. Test plan
Fixtures: `people_config`, `ctx`, `fake_core` and `fake_room` (SPEC-01). `run_close(ctx)` is SPEC-12's
`handle_close_start` with the October intent and `LEAD`; after it, roots are `m-3`…`m-6`. `D = ctx.display`, and
`L = fake_room.link`.

**`tests/room/test_resume.py`**

| Test | Act | Assert |
|---|---|---|
| `test_resume_line_lists_open_gaps_with_links_and_posts_no_roots` | `run_close`; then `room2 = FakeRoom()`, `ctx2 = dataclasses.replace(ctx, room=room2)` (simulating a restart with the same core); `await resume(ctx2, "2026-10-v1")` | `room2.posts` is one carbon-room top-level post equal to SPEC-05's E-RESUME text (`"Resuming the October 2026 close at AWAITING_HUMANS.\nOpen gaps: G-1 @priya (message m-3) · G-2 @lead (message m-4) · G-3 @lead (message m-5) · G-4 @lead (message m-6)"`); no `record_gap_thread` call after the close [1] |
| `test_resume_posts_missing_root_once` | `run_close`; set `fake_core.on_resolve_open` to SPEC-01's R7 finding; `fake_core.resolve("G-4", "approve", LEAD, "h-2", {})`; then `resume(ctx2, cid)` twice | after the first resume: a resume line containing `"G-5 @finance (no thread yet)"`, then one watchdog root starting `"**G-5 · FINANCE**"` with no `"Evidence:"`; after the second: only one more post, a resume line containing `"G-5 @finance (message m-2)"`, where `m-2` is room2's id for that root [1] |
| `test_handle_resume_no_close` | a fresh core; `handle_resume` with message `h-1` | the carbon-room post in thread `h-1` is `no_close()` [2] |
| `test_handle_resume_does_not_begin_close` | `run_close`; `handle_resume` | `fake_room.closes == ["2026-10-v1"]` (only the close itself) [2] |
| `test_resume_on_startup_true_false_published` | (a) a fresh core; (b) after `run_close` on ctx2; (c) after `fake_core.draft_report(cid)` and `fake_core.publish(cid, LEAD, "h-9")` | (a) False, no posts; (b) True, `room2.closes == ["2026-10-v1"]`, one resume line; (c) False, no new posts [3] |

**`tests/room/test_notices.py`**

| Test | Act | Assert |
|---|---|---|
| `test_warn_label_from_config` | `people_config` (warn_at 0.8); then a tmp config with `budgets: {warn_at: 0.75}` | `"80%"`; `"75%"` [4] |
| `test_warn_label_default_without_config` | a config dir without `carbon_room.yaml` | `"80%"` [4] |
| `test_budget_warn_once_then_stopped_once` | `run_close`; `fake_core.budget = {"collector": {"used": 160000, "limit": 200000, "state": "warn"}, "watchdog": {"used": 1, "limit": 200000, "state": "ok"}}`; call `check_budgets` twice; set collector to `stopped`; call twice more | the results are `["@collector has used 80% of its budget for this close."]`, `[]`, `["@collector has hit its budget for this close and has stopped. The Lead can raise it in config."]`, `[]`; both posts are carbon-room, top level, `essential is False` [5, 6] |
| `test_budget_notices_sorted_by_agent` | `budget = {"watchdog": {…, "state": "warn"}, "collector": {…, "state": "warn"}}` | `check_budgets` | the collector notice comes first [5] |
| `test_new_close_warns_again` | the warn notice sent for `2026-10-v1`; then `fake_core.start_close` a v2 with the same budget dict | `check_budgets(ctx, "2026-10-v2")` | one notice [5] |

**`tests/room/test_noise.py`** (`inner = FakeRoom()`; `g = NoiseGuard(inner, max_posts=12, reserve=2)`)

| Test | Act | Assert |
|---|---|---|
| `test_noise_full_scripted_close_at_most_12_top_level` | `g.begin_close("c")`; 7 essential posts `e1`…`e7`; 4 non-essential `t1`…`t4`; essential `draft`; essential `publish` | `len(inner.top_level()) == 12`; `t1`, `t2` and `t3` were posted on their own; `t4` returned `""`; the 11th post's text is `"t4\n\ndraft"`; the 12th is `"publish"`; `g.top_level_count == 12` [7] |
| `test_noise_thread_posts_not_counted` | 20 posts with `thread_id="m-1"`, non-essential | all 20 reach `inner`; `top_level_count == 0` [7] |
| `test_noise_essential_always_sent` | 15 essential top-level posts | all 15 sent; a WARNING containing `"limit 12"` logged at least once [7] |
| `test_noise_buffer_joins_multiple` | `max_posts=3, reserve=2`; `e1`, `t1` (buffered), `t2` (buffered), `e2` | the second sent post is `"t1\nt2\n\ne2"` [7] |
| `test_begin_close_resets` | fill to the threshold, buffer one, then `begin_close("c2")` | count 0, `buffered == []`; `inner.closes[-1] == "c2"`; a non-essential post now goes out [7] |
| `test_noise_delegates` | — | `send_targeted`, `upsert_doc` and `link` | land on `inner` unchanged; `isinstance(g, Room)` [7] |
| `test_max_posts_from_config` | `people_config`; then a config without `noise` | `max_posts_from_config()` | `12`; `12` [8] |

**`tests/room/test_board.py`**

| Test | Act | Assert |
|---|---|---|
| `test_board_after_close` | `run_close`; `update_board(ctx, cid)` | True; `fake_room.docs["close-board"]` equals SPEC-05's E-BOARD [9] |
| `test_board_matches_summary_after_each_resolution` | `run_close`; then the four resolutions directly on `fake_core` (SPEC-01's table), calling `update_board` after each | after each, `docs["close-board"] == board("October 2026", fake_core.summary(cid), D, L)`; the final board contains `"Coverage: 100%"` and `"No open gaps."` [9] |
| `test_board_unsupported_returns_false_and_posts_nothing` | `ctx.room = FakeRoom(supports_docs=False)` | `update_board` | False; `posts == []`; `docs == {}` [9] |
| `test_after_phase_swallows_errors` | `run_close`; `fake_core.fail["summary"] = RuntimeError("x")`; `fake_core.budget` set to a collector warn | `await after_phase(ctx, cid)` | no exception; an ERROR record; the budget notice was still posted [10] |
| `test_after_phase_runs_board_then_budgets` | `run_close`; clear `fake_core.calls` | `after_phase` | call names `["summary", "budget_usage"]` [10] |

## 7. Fixtures and doubles
`FakeCore` (with `budget`, `fail` and `on_resolve_open`), `FakeRoom` (including `supports_docs=False`) and the
SPEC-01 fixtures. Tmp config dirs are written by the tests that need them.

## 8. Manual check
- Kill `make run` mid-close and start it again. The room shows one "Resuming the October 2026 close at …" line
  with links to the existing threads, and no repeated roots.
- With S6 passed, open the room's documents in Switch Console or Mattermost and see `close-board`.

## 9. Done when
- [ ] Kill-and-restart (simulated: a new room, the same core) shows the resume line with the right gaps
- [ ] With a tiny budget, the warning appears once
- [ ] A full scripted close stays at or under 12 top-level posts
- [ ] The board matches `summary()` after each of the four resolutions
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on the touched paths
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Wiring `NoiseGuard` and `after_phase` into the runtime (SPEC-15).
- Lock notices. `LockHeld` is already replied to by SPEC-13 and SPEC-15 through `errors.reply_for`.

## 11. Open questions
None block execution.
