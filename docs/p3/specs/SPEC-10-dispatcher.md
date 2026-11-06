# SPEC-10 · Dispatcher and worker lanes
Stories: P3-2.4, plus P1's replay-protection ask · Branch: `p3-s10-dispatcher` · PR title: "P3-S10 (2.4): dispatcher and worker lanes"
Depends on (must be merged): SPEC-01, SPEC-02, SPEC-06 · Wave: 2 · Estimated session time: 1 h

## 1. Goal
One asyncio pipeline takes raw frames from the four sockets. It decodes them and drops what isn't ours. It
deduplicates by message id, since the same message arrives on several sockets and again on replay. It classifies
what remains, then runs mutations one at a time in arrival order and reads concurrently. Handler errors go to
`on_error`. Nothing here blocks the event loop.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.4, §3.5, §3.6 and §3.13
- `docs/HANDOFF.md` (the "P3 must … enforce … event replay protection" sentence)
- `carbon_room/room/events.py` (`RoomEvent`), `carbon_room/room/grammar.py` (`Intent`) and
  `carbon_room/room/async_core.py`

## 3. Files
- Create `carbon_room/room/dispatch.py`
- Create `tests/room/test_dispatch.py`

## 4. Public interface
```python
MUTATING_KINDS: frozenset[str] = frozenset({"close.start", "close.resume", "close.publish", "report.draft",
                                            "gap.reply", "gap.fallback"})

class Dispatcher:
    def __init__(self, *, decode: Callable[[str, dict], RoomEvent | None],
                 classify: Callable[[RoomEvent], Intent],
                 handle: Callable[[RoomEvent, Intent], Awaitable[None]],
                 on_error: Callable[[RoomEvent, Intent, BaseException], Awaitable[None]],
                 room_id: str, max_reads: int = 4, seen_limit: int = 5000) -> None
    def submit(self, agent_name: str, frame: dict) -> None   # sync, non-blocking; used as on_event
    async def run(self) -> None
    async def join(self) -> None
    async def stop(self) -> None
    handled_count: int                                        # events handed to a lane so far
```

## 5. Behaviour
1. **`submit`** calls `put_nowait((agent_name, frame))` on an unbounded `asyncio.Queue` created in `__init__`.
   It never awaits, never raises, and must be called on the loop's thread.
2. **Intake.** `run()` takes items from the intake queue in order. For each item it runs the pipeline below,
   all synchronously within the intake task.
   1. **Decode.** `event = decode(agent_name, frame)`. Drop the item if `event` is None or
      `event.type != "message"`. If decode raises, log a WARNING and drop the item.
   2. **Room.** Drop it if `event.room_id != room_id`, with a DEBUG log.
   3. **Handled already.** Drop it if `event.message_id` is in the handled set, with a DEBUG log.
   4. **Classify.** `intent = classify(event)`.
      - If classify raises, log a WARNING and drop the item.
      - If `intent.kind == "ignore"`, drop it **without** marking the id. A later copy of the same message (say
        on the addressed agent's socket) can still be accepted.
   5. **Mark.** Add `event.message_id` to the handled set. This is an `OrderedDict`; past `seen_limit` entries,
      the oldest are evicted.
   6. **Route.** Kinds in `MUTATING_KINDS` go onto a FIFO mutation queue served by **one** worker task. Every
      other kind runs as its own task, with at most `max_reads` running at once (an `asyncio.Semaphore`).
      `handled_count += 1`.
3. **Running a handler.** `await handle(event, intent)`.
   - An `Exception` goes to `await on_error(event, intent, exc)`.
   - An exception inside `on_error` is logged at ERROR with its traceback and swallowed.
   - `asyncio.CancelledError` is never passed to `on_error`.
4. **Ordering.**
   - Two mutations never overlap: the second starts only after the first has finished, success or failure. They
     run in the order their frames passed step 5.
   - Reads may run while a mutation runs.
5. **`join()`** returns when the intake queue is empty, the mutation queue is empty, no mutation is running and no
   read task is running. Tests use it to wait for quiet.
6. **`stop()`.**
   - Stops intake: later `submit` calls are ignored with a DEBUG log.
   - Lets the running mutation finish.
   - Drops the mutations still queued, with one WARNING `dropping <n> queued mutation(s) on stop`.
   - Cancels running read tasks.
   - Then `run()` returns. `stop()` returns once all of this is done.
7. **No blocking.** The dispatcher does no blocking I/O. Handlers that call core use `AsyncCore`, so the loop stays
   responsive.

## 6. Test plan
Test doubles, defined in the test module:
- `ev(message_id, *, room="room-1", agent="watchdog", type="message", body="x")` builds a `RoomEvent` with the
  other fields filled with simple defaults.
- `decode(agent, frame)` returns `frame["event"]` with `receiving_agent=agent` (use `dataclasses.replace`), or
  None when `frame` has no `"event"`.
- `classify(event)` returns `Intent(event.body, {}, "carbon-room")`, so the body *is* the kind. A body of
  `"ignore@watchdog"` returns `ignore` when the receiving agent is watchdog and `ask` otherwise.
- `Recorder` keeps `starts` and `ends` lists, and an optional `sleep` per kind. Its `handle` appends
  `(kind, message_id)` to `starts`, awaits the sleep, then appends to `ends`.

Each test runs `asyncio.run(main())`. `main` starts `d.run()` as a task, submits, awaits
`asyncio.wait_for(d.join(), 3)`, then `await d.stop()`.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_slow_core_call_does_not_delay_loop` | `handle` awaits `AsyncCore(FakeCore(delay=1.0)).latest_close()`; a probe task loops `await asyncio.sleep(0.05)` and records the lateness of each tick | submit one `close.start` event; run the probe for 1.2 s | the handler finished; the probe's largest lateness is < 0.2 s [7] |
| `test_two_resolves_same_close_run_in_order` | `sleep = {"gap.reply": 0.1}` | submit `gap.reply` events `a` then `b` | `starts == [("gap.reply", "a"), ("gap.reply", "b")]`; the time `b` started ≥ the time `a` ended [2.6, 4] |
| `test_mutations_fifo_across_kinds` | `sleep = {"close.start": 0.1}` | submit `close.start` `a`, `gap.fallback` `b`, `report.draft` `c` | `starts` order is `a, b, c`, with no overlap [4] |
| `test_reads_run_concurrently_with_mutation` | `sleep = {"gap.reply": 0.3, "ask": 0.0}` | submit `gap.reply` `a`, then `ask` `b` | `b` ended before `a` ended [2.6, 4] |
| `test_reads_capped_by_max_reads` | `max_reads=2`; `sleep = {"ask": 0.2}`; a gauge of concurrently running asks | submit 5 asks | the peak gauge value is 2; all 5 ended [2.6] |
| `test_duplicate_message_id_handled_once` | — | submit the same `close.start` `m1` from `carbon-room`, then from `watchdog`, then again (a replay after reconnect) | `starts == [("close.start", "m1")]`; `handled_count == 1` [2.3, 2.5] |
| `test_ignored_copy_does_not_block_addressed_copy` | body `"ignore@watchdog"` | submit `m1` as received by `watchdog`, then `m1` as received by `carbon-room` | one start for `m1`, with kind `ask` [2.4] |
| `test_other_room_dropped` | — | submit `ev("m1", room="room-2")` | `starts == []` [2.2] |
| `test_non_message_dropped` | — | submit `ev("j1", type="room_join")` and a frame with no `"event"` (decode gives None) | `starts == []` [2.1] |
| `test_decode_or_classify_error_is_logged_and_dropped` | `decode` raises for frame `{"boom": 1}`; `classify` raises for body `"explode"` | submit both, then a good `ask` `m3` | only `m3` started; 2 WARNING records [2.1, 2.4] |
| `test_handler_exception_goes_to_on_error` | `handle` raises `ValueError("bad")` for `m1` | submit `gap.reply` `m1`, then `gap.reply` `m2` | `on_error` called once with `(event m1, intent, exc)` where `str(exc) == "bad"`; `m2` still handled [3, 4] |
| `test_on_error_failure_is_logged_not_raised` | `handle` raises; `on_error` raises `RuntimeError("x")` | submit 1, then another good one | an ERROR record; the good one is still handled; `run()` didn't crash [3] |
| `test_seen_limit_evicts_oldest` | `seen_limit=2` | submit `ask` `m1`, `m2`, `m3`, then `m1` again | `m1` is handled twice (evicted, then accepted again); `m3` once [2.5] |
| `test_submit_never_blocks` | — | outside any handler, time 1000 `submit` calls | total < 0.05 s, and each call returns None [1] |
| `test_stop_waits_for_inflight_mutation` | `sleep = {"gap.reply": 0.3}` | submit `gap.reply` `a` and `b`; once `a` has started, `await d.stop()` | `a` is in `ends`; `b` never started; a WARNING `dropping 1 queued mutation(s) on stop` [6] |
| `test_stop_cancels_reads` | `sleep = {"ask": 5}` | submit an ask; once started, `await stop()` | `stop()` returns in < 1 s; the ask isn't in `ends`; `on_error` wasn't called [3, 6] |
| `test_submit_after_stop_ignored` | — | `stop()`, then `submit(...)` | no error; nothing handled [6] |

The whole module runs in under 6 s.

## 7. Fixtures and doubles
`FakeCore` (with `delay`) and `AsyncCore` from SPEC-01, in the first test only. Everything else uses in-test
doubles.

## 8. Manual check
None. SPEC-15's loop test covers the real wiring.

## 9. Done when
- [ ] A 5-second fake core call doesn't delay a pong. The loop-lag probe shows this here; SPEC-07 covers the socket
- [ ] Two resolves for the same close run in order
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
The real `decode`, `classify` and `handle` (SPEC-06 and SPEC-15), and replying to errors (SPEC-15 `on_error`).

## 11. Open questions
None. One FIFO worker for all mutations serialises every close. Only one close runs at a time, so this meets
story 2.4's "one lock per close".
