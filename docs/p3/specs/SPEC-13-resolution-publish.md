# SPEC-13 · Resolution, publish, reports and ask
Stories: P3-4.5, P3-4.6, P3-5.4, plus status, trace, audit and help · Branch: `p3-s13-resolution` · PR title: "P3-S13 (4.5, 4.6, 5.4): resolution, publish, reports and ask"
Depends on (must be merged): SPEC-04, SPEC-11, SPEC-12 (and so SPEC-01, -02, -05, -06) · Wave: 3 · Estimated session time: 2 h

> **Uses the SPEC-05 contract change.** `old_close_gap` guards against a reply in a thread from an earlier close.
> `core.resolve` has no `close_id` and acts on the latest close, so such a reply would change the wrong gap.

## 1. Goal
This spec holds the handlers for everything a person does after the close starts:
- reply in a gap thread, or use `G-n …` anywhere, to resolve a gap
- draft and publish the report
- ask for status, a trace or an audit check
- ask help
- ask the ledger a free-text question

Every human-triggered core call carries the actor and `event.message_id`. Replies go where people expect them:
gap replies in the gap's thread, command replies in the command's thread, and the "total moved" line at top level.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.3, §3.8, §3.9, §3.14, §3.15 and §3.16
- `00-CONTRACTS.md` §4, §6 and §7
- `carbon_room/room/{messages,errors,router,attachments,events,grammar,ports}.py` and
  `carbon_room/agents/{gaps,orchestrator}.py`
- `tests/fakes/fake_core.py`, `tests/fakes/fake_room.py` and `tests/room/conftest.py`

## 3. Files
- Create `carbon_room/agents/resolution.py`, `carbon_room/agents/publish.py`, `carbon_room/agents/reports.py` and
  `carbon_room/agents/ask.py`
- Create `tests/room/test_resolution.py`, `tests/room/test_publish.py`, `tests/room/test_reports.py` and
  `tests/room/test_ask.py`

## 4. Public interface
Every handler has the signature `async def h(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) ->
None`.

```python
# resolution.py
async def handle_gap_reply(ctx, event, intent, actor) -> None        # intents gap.reply and gap.fallback
# publish.py
async def handle_draft(ctx, event, intent, actor) -> None
async def handle_publish(ctx, event, intent, actor) -> None
async def list_outputs(out_dir: Path, close_id: str, version: int) -> list[str]
# reports.py
async def handle_status(ctx, event, intent, actor) -> None
async def handle_trace(ctx, event, intent, actor) -> None
async def handle_verify_audit(ctx, event, intent, actor) -> None
async def handle_help(ctx, event, intent, actor) -> None
# ask.py
async def handle_ask(ctx, event, intent, actor) -> None
```

"Command thread" means `event.thread_id or event.message_id` throughout.

## 5. Behaviour

### `handle_gap_reply` (posts as watchdog unless stated)
1. **Find the gap.**
   - **`gap.reply`:**
     - If `event.thread_id` is None, return.
     - `gap = await core.gap_for_thread(event.thread_id)`. If it is None, return silently (DEBUG log): the reply
       was in a thread that isn't a gap.
     - `latest = await core.latest_close()`. If `gap.close_id != latest`, reply `old_close_gap(gap)` in the
       gap's thread and stop.
     - `close_id = gap.close_id`.
   - **`gap.fallback`:**
     - `close_id = await core.latest_close()`. If it is None, reply `no_close()` in the command thread and stop.
     - `_, open_gaps = await core.resume_state(close_id)`, then
       `gap = router.find_gap(open_gaps, intent.args["gap_id"])`.
     - If no gap is found, reply `gap_not_found(intent.args["gap_id"])` in the command thread and stop.
2. **Reply thread.** From here on, every watchdog reply goes to
   `thread = gap.thread_root_message_id or event.thread_id or event.message_id`.
3. **Guests.** When `actor.role is None`, reply
   `errors.reply_for(NotAllowed("guest"), owner_name=ctx.display(gap.owner)).text` and stop. No further core call
   is made.
4. **Match.** `m = router.match_reply(gap, intent.args["text"], bool(event.attachments))`.
   - `NoMatch("unknown_reply")` replies `options_help(gap)`.
   - `NoMatch("gap_resolved")` replies `already_resolved(gap)`.
   - `NoMatch("no_options")` replies `no_reply_needed()`.
   - Each of these stops here.
5. **Resolve.**
   1. Reply `checking()`.
   2. `payload = dict(m.payload)`.
   3. **Upload.** When `m.option.action == "upload"`, set
      `payload["path"] = str(await attachments.fetch(message_id=event.message_id,
      attachment=event.attachments[0] if event.attachments else None, typed_name=m.filename,
      mode=ctx.attachments_mode, inbox_dir=ctx.inbox_dir, download=ctx.download))`. On `AttachmentMissing`,
      reply its `text` and stop.
   4. `before = await core.summary(close_id)`.
   5. `findings = await core.resolve(gap.gap_id, m.option.action, actor, event.message_id, payload)`.
   6. A `CarbonRoomError` or `ValueError` raised in steps 4–5 replies
      `reply_for(exc, owner_name=ctx.display(gap.owner)).text` and stops. Other exceptions propagate to
      `app.on_error`.
6. **Outcome.**
   - `_, open_after = await core.resume_state(close_id)`.
   - If `gap.gap_id` is not among `open_after`'s ids, reply `outcome_resolved(gap)`.
   - Otherwise reply `outcome_open(gap, reason)`. `reason` is the `title` of the finding in `findings` with
     `finding_id == gap.finding_id`, or `"the next check still flags it"` when there is none.
7. **Follow-up.**
   1. `await gaps.post_new_gaps(ctx, close_id, findings)`.
   2. `after = await core.summary(close_id)`. If `after.verified_kgco2e != before.verified_kgco2e` or
      `after.coverage_pct != before.coverage_pct`, carbon-room posts `total_moved(before, after)` at top level
      with `essential=False`. An unchanged total posts nothing.
   3. `await ctx.on_phase_end(close_id)`.

### `publish.py`
8. **`handle_draft`** (as reporter).
   - `close_id = await core.latest_close()`. If it is None, reply `no_close()` in the command thread and stop.
   - `report = await core.draft_report(close_id)`.
   - Post `draft(report, month_label(month_of(close_id)))` at top level.
   - Then `await ctx.on_phase_end(close_id)`.
9. **`handle_publish`** (as carbon-room).
   1. **Guests.** When `actor.role is None`, reply `reply_for(NotAllowed("guest")).text` ("Only the Lead can do
      that.") in the command thread and stop. No core call is made.
   2. `close_id = await core.latest_close()`. If it is None, reply `no_close()` in the command thread and stop.
   3. `phase, _ = await core.resume_state(close_id)`. If `phase != "DRAFTED"`, first
      `await core.draft_report(close_id)`.
   4. `report = await core.publish(close_id, actor, event.message_id)`. A `NotAllowed` replies
      `reply_for(exc).text` in the command thread and stops. Other exceptions propagate.
   5. `paths = await list_outputs(ctx.out_dir, close_id, report.version)`.
   6. Post `published(report, ctx.display(actor.id), paths)` at top level.
   7. `await ctx.on_phase_end(close_id)`.
10. **`list_outputs(out_dir, close_id, version)`** runs in a worker thread. It lists every regular file under
    `out_dir / month_of(close_id) / f"v{version}"`, recursively, as `p.as_posix()`, sorted. Relative stays
    relative. A missing directory gives `[]`.

### `reports.py` (every reply goes in the command thread)
11. **Agents.** `handle_status` posts as carbon-room. `handle_trace` and `handle_verify_audit` post as reporter.
    `handle_help` posts as `intent.target_agent or "carbon-room"`.
12. **No close.** Each handler except `handle_help` first does `close_id = await core.latest_close()`. If it is
    None, it replies `no_close()` and stops.
13. **`handle_status`** posts `summary_post(month_label(month_of(close_id)), await core.summary(close_id),
    ctx.display)`.
14. **`handle_trace`.**
    - `tag = await core.trace(close_id, intent.args["tag"])`, then post `trace_card(tag,
      ctx.room.link(tag.chat_message_id) if tag.chat_message_id else None)`.
    - A `NotFound` replies `tag_not_found(intent.args["tag"])`.
15. **`handle_verify_audit`** posts `audit_result(await core.verify_audit(close_id))`.
16. **`handle_help`** posts `help_text(intent.args.get("reason"))`, with no core call.

### `ask.py`
17. **`handle_ask`** posts as `agent = intent.target_agent or "carbon-room"`, in the command thread.
    - If there is no close, it replies `no_close()`.
    - Otherwise it posts `await core.explain(close_id, intent.args["question"], actor)` verbatim.

### All handlers
18. **Boundaries.** Handlers never compute a figure, never import `carbon_room.core` or `carbon_room.ledger`, and
    never read a role, user id or message id from message text. The actor and `event.message_id` are passed
    straight to core.

## 6. Test plan
**Shared helpers.** Each test module defines its own copies, because module basenames must be unique and helpers
must not go in conftest:
- `LEAD = Actor("human", "lead", "Sustainability Lead", "lead")`, `PRIYA = Actor("human", "priya", "Priya",
  "site_manager")` and `GUEST = Actor("human", "guest:@x:test", "x", None)`.
- `make_event(body, *, message_id, thread_id=None, attachments=(), receiving_agent="watchdog")` builds a
  `RoomEvent`.
- `run_close(ctx, message_id="h-1")` calls `handle_close_start` (SPEC-12) with `Intent("close.start", {"month":
  "2026-10"}, "carbon-room")` and `LEAD`.
- `root(fake_room, gap_id)` returns the message id of the top-level watchdog post that starts with
  `f"**{gap_id} "`. Search the posts newest first, so after a second close the newest root wins.
- `reply(ctx, actor, body, *, thread, message_id, attachments=())` builds the event and intent
  (`grammar.parse(body, in_thread=True, today=date(2026, 11, 5))`) and awaits `handle_gap_reply`.

Every test requests `people_config`, `ctx`, `fake_core` and `fake_room`. Unless stated otherwise, it starts with
`await run_close(ctx)`, after which G-1…G-4 have roots `m-3`…`m-6`.

**`tests/room/test_resolution.py`**

| Test | Act | Assert |
|---|---|---|
| `test_pick_a_in_diesel_thread_calls_resolve_with_option_a` | LEAD `pick a` in `root("G-2")`, message `h-2` | `("resolve", {"gap_id": "G-2", "action": "pick", "actor": LEAD, "chat_message_id": "h-2", "payload": {"claim_id": "CL-0003"}})` is in `fake_core.calls`; the posts in thread `m-4` are `["Checking…", "Resolved. G-2 is closed and the ledger is updated."]`, both by watchdog [4–6] |
| `test_hello_in_gap_thread_lists_options_and_no_resolve` | LEAD `hello` in `m-4` | the thread `m-4` holds exactly ``"I didn't catch that. Reply with one of: `pick A`, `pick B`."``; no `resolve` and no `summary` call after the close [4] |
| `test_already_resolved_and_no_options` | pick A on G-2, then `pick B` again in `m-4`; separately, a G-5 with no options (from `on_resolve_open`, a copy of SPEC-01's R6 finding with id `F-0000000008`) after its root is posted | `"G-2 is already resolved."`; `"No reply needed here."` in G-5's thread [4] |
| `test_reply_outside_a_gap_thread_is_silent` | LEAD `pick a` in thread `m-7` (the summary post) | no new posts; no `resolve` call [1] |
| `test_fallback_in_channel_routes_and_replies_in_gap_thread` | `await run_close(ctx, "h-1")`, then `await run_close(ctx, "h-8")` (close v2, roots `m-10`…`m-13`); then a `gap.fallback` event, `G-2 pick A`, top level, message `h-9`, LEAD | the replies are in thread `m-11` (v2's G-2): `["Checking…", "Resolved. G-2 is closed and the ledger is updated."]`; `fake_core.resume_state("2026-10-v1")[1]` still contains G-2 [1, 2] |
| `test_reply_in_old_close_thread_is_refused` | two closes as above; LEAD `pick a` in `m-4` (v1's G-2 root) | the thread `m-4` gets `"G-2 belongs to an earlier close (2026-10-v1). Reply in the thread from the current close."`; no `resolve` call [1] |
| `test_fallback_unknown_gap_and_no_close` | `G-9 approve` top level, message `h-3`; and with a fresh `FakeCore` (no close), `G-2 pick A` message `h-4` | `"I can't find an open G-9 in this close."` in thread `h-3`; the `no_close()` text in thread `h-4` [1] |
| `test_guest_refused_without_core_call` | `n = len(fake_core.calls)`; GUEST `pick a` in `m-4` | thread `m-4` holds `"Only the Lead or the gap owner (@lead) can do that."`; the only new calls are `gap_for_thread` and `latest_close` [3] |
| `test_priya_resolving_g2_is_not_allowed` | PRIYA `pick a` in `m-4` | posts in `m-4`: `["Checking…", "Only the Lead or the gap owner (@lead) can do that."]` (the fake raises `NotAllowed`) [5.6] |
| `test_upload_with_inbox_file_passes_path` | `monkeypatch.chdir(tmp_path)`; write `data/inbox/warehouse2_electricity_2026-10_actual.pdf`; PRIYA in `m-3`, body `""`, attachment `Attachment("warehouse2_electricity_2026-10_actual.pdf", "application/pdf", 10, "mxc://s/1", "m.file")`, message `h-2` | the `resolve` call has `gap_id "G-1"`, `action "upload"`, `actor PRIYA`, `chat_message_id "h-2"` and `payload {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh", "path": "data/inbox/warehouse2_electricity_2026-10_actual.pdf"}` [5.3] |
| `test_upload_typed_name_inbox` | the same file; PRIYA in `m-3`, body `upload warehouse2_electricity_2026-10_actual.pdf`, no attachment | the same payload path [5.3] |
| `test_upload_missing_file_exact_text` | `monkeypatch.chdir(tmp_path)`, an empty inbox; the same attachment | the posts in `m-3` are `["Checking…", "I can't see that file yet. Put it in data/inbox/ and reply upload warehouse2_electricity_2026-10_actual.pdf."]`; no `resolve` call [5.3] |
| `test_outcome_resolved_and_still_open` | `fake_core.keep_open = {"G-4"}`; LEAD `approve` in `m-6`; then LEAD `pick a` in `m-4` | `m-6` ends with `"G-4 is still open: HQ October electricity is 38% above September."`; `m-4` ends with `"Resolved. G-2 is closed and the ledger is updated."` [6] |
| `test_new_gaps_from_resolve_are_posted` | `fake_core.on_resolve_open = [R7]` (SPEC-01's finance finding); LEAD `approve` in `m-6` | a new top-level watchdog post equals `gap_root(<G-5 from resume_state>, R7, "@finance")`; G-5 now has a root [7.1] |
| `test_total_moved_posted_once_when_changed` | `before = len(fake_room.top_level())`; LEAD `pick a` in `m-4` | exactly one new top-level post: carbon-room, `essential is False`, text `"Total moved 0.0 → 5.3 tCO2e, coverage 0% → 23%."` [7.2] |
| `test_reject_posts_no_total_line` | LEAD `reject: not ours` in `m-5` | no new top-level post; the `resolve` payload is `{"reason": "not ours"}` [7.2] |
| `test_four_scripted_resolutions_reach_fake_final_totals` | `monkeypatch.chdir(tmp_path)` with the demo file in `data/inbox/`; PRIYA uploads in `m-3`; LEAD `pick A` in `m-4`; LEAD `approve` in `m-5`; LEAD `approve` in `m-6` | `fake_core.summary("2026-10-v1")` has verified `Decimal("22900")` and coverage `Decimal("100")`; the non-essential top-level texts are, in order, `"Total moved 0.0 → 3.6 tCO2e, coverage 0% → 12%."`, `"Total moved 3.6 → 8.9 tCO2e, coverage 12% → 39%."`, `"Total moved 8.9 → 13.2 tCO2e, coverage 39% → 58%."` and `"Total moved 13.2 → 22.9 tCO2e, coverage 58% → 100%."` [Done when] |
| `test_resolve_error_replied_in_thread` | `fake_core.fail["resolve"] = LockHeld("x")`; LEAD `pick a` in `m-4` | `m-4`: `["Checking…", "@collector is still reading that source. Try again in a moment."]` [5.6] |
| `test_unexpected_error_propagates` | `fake_core.fail["resolve"] = RuntimeError("boom")` | `handle_gap_reply` raises `RuntimeError` [5.6] |
| `test_on_phase_end_after_resolution` | a recorder as `ctx.on_phase_end`; LEAD `pick a` in `m-4` | the recorder got `["2026-10-v1"]` from this reply [7.3] |

**`tests/room/test_publish.py`**

| Test | Act | Assert |
|---|---|---|
| `test_draft_posts_headline` | `handle_draft` (LEAD, message `h-5`, intent `report.draft`) | one new top-level reporter post equal to `draft(fake_core.draft_report("2026-10-v1"), "October 2026")`; it starts with `"**Draft v1 for October 2026**"` [8] |
| `test_lead_publishes_and_paths_listed` | `monkeypatch.chdir(tmp_path)`; create `out/2026-10/v1/report.md` and `out/2026-10/v1/coverage.html`; `ctx.out_dir = Path("out")`; `handle_publish` LEAD `h-6` | the new top-level carbon-room post is exactly `"Published v1 by @lead.\nVerified: 0.0 tCO2e · Coverage: 0% · 0 of 4 expected sources verified\nPublished with 4 open gap(s); their rows are excluded.\nFiles: out/2026-10/v1/coverage.html, out/2026-10/v1/report.md"`; the `publish` call has `actor LEAD` and `chat_message_id "h-6"` [9, 10] |
| `test_publish_drafts_first_when_needed` | `handle_publish` LEAD; separately, `handle_draft` first and then `handle_publish` | the call names after the close are `["latest_close", "resume_state", "draft_report", "publish"]`; for the second case, `[…, "latest_close", "resume_state", "publish"]` with no second `draft_report` [9.3] |
| `test_guest_publish_refused` | `n = len(fake_core.calls)`; `handle_publish` GUEST `h-6` | thread `h-6` has the carbon-room post `"Only the Lead can do that."`; `len(fake_core.calls) == n` [9.1] |
| `test_priya_publish_not_allowed_text` | `handle_publish` PRIYA `h-6` | thread `h-6`: `"Only the Lead can do that."`; no top-level post added [9.4] |
| `test_list_outputs` | `tmp_path/out/2026-10/v1/a.txt` and `.../sub/b.txt`; a missing `v2` | `list_outputs(tmp_path / "out", "2026-10-v1", 1)` | the two posix paths, sorted; `[]` for version 2 [10] |
| `test_draft_and_publish_no_close` | a fresh `FakeCore` in ctx | `handle_draft` (`h-1`), `handle_publish` LEAD (`h-2`) | `no_close()` in thread `h-1` as reporter and in `h-2` as carbon-room [8, 9] |

**`tests/room/test_reports.py`**

| Test | Act | Assert |
|---|---|---|
| `test_status_reply_in_thread` | `handle_status`, message `h-5` | the post in thread `h-5`, as carbon-room, equals `summary_post("October 2026", fake_core.summary("2026-10-v1"), ctx.display)` [13] |
| `test_status_inside_a_thread_replies_there` | `handle_status` with `thread_id="m-4"` | the post is in thread `m-4` [11] |
| `test_trace_card_and_unknown_tag` | resolve directly on `fake_core` as in SPEC-01's table (messages `h-2`…`h-5`), then `fake_core.draft_report`; `handle_trace` with tag `S-001`, then `S-099` | the first reporter post equals `trace_card(fake_core.trace("2026-10-v1", "S-001"), "message h-5")`; the second is `"I can't find S-099 in this close."` [14] |
| `test_verify_audit_reply` | `fake_core.audit = AuditCheck(False, 9, 4)`; `handle_verify_audit` `h-5` | thread `h-5`: `"Audit chain broken at event 4 (9 events checked)."` as reporter [15] |
| `test_help_reply_uses_target_agent` | no close needed; `handle_help` with `Intent("help", {"reason": "I don't know the month 'Smarch'."}, "watchdog")` | watchdog post in the thread equals `help_text("I don't know the month 'Smarch'.")`; no core calls [16] |
| `test_no_close_replies` | a fresh `FakeCore` | `handle_status`, `handle_trace`, `handle_verify_audit` | each replies `no_close()` in its thread, as carbon-room, reporter and reporter [12] |

**`tests/room/test_ask.py`**

| Test | Act | Assert |
|---|---|---|
| `test_ask_unknown_before_upload_names_priya` | `handle_ask` with `Intent("ask", {"question": "what is Warehouse-2 October electricity?"}, "collector")`, `h-7` | the collector post in thread `h-7` is `"UNKNOWN for warehouse-2, because no VERIFIED ledger rows match, owned by priya"`; the `explain` call has `close_id "2026-10-v1"` and `actor LEAD` [17] |
| `test_ask_verified_after_upload` | `fake_core.resolve("G-1", "upload", PRIYA, "h-2", {"path": "x", **G-1 params})`, then the same ask | `"Verified ledger facts: CL-0010: warehouse-2 18000 kWh, 3600 kgCO2e, status VERIFIED"` [17] |
| `test_ask_replies_in_question_thread` | the ask with `thread_id="m-4"` | the post is in `m-4` [17] |
| `test_ask_no_close` | a fresh `FakeCore` | `handle_ask` | `no_close()` as collector [17] |

## 7. Fixtures and doubles
`FakeCore` (with the `fail`, `keep_open`, `on_resolve_open` and `audit` hooks), `FakeRoom`, `ctx` and
`people_config` from SPEC-01. The demo upload is written by the tests as a few bytes; the real PDF isn't needed.

## 8. Manual check
After SPEC-15, in the real room with the real core (S18):
- Reply `hello` in a gap thread. You get the options.
- Reply `pick A` in the diesel thread. You see `Checking…`, then `Resolved…`, then one top-level `Total moved …`.
- `@carbon-room publish` from Priya's account is refused.
- `@collector what is Warehouse-2 October electricity?` is UNKNOWN, naming Priya.

## 9. Done when
- [ ] Against the fake core, the four scripted resolutions move the total to the fake final figure. The real-core
      version is S18
- [ ] An unchanged total posts no top-level line
- [ ] A lead can publish, and a guest gets a clear refusal
- [ ] The ask answer is UNKNOWN naming Priya before the upload, and a verified figure after it
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on the four new `carbon_room/agents` files and `tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Deciding which socket accepts an event (SPEC-15), posting through Switch (SPEC-15), and the noise guard and
  board (SPEC-14).
- Answering a follow-up question asked in a non-gap thread without a mention. It is silently ignored (rule 1).

## 11. Open questions
None block execution. P2 question 1 (plan §1.4): rule 1's old-close guard makes the "latest close" assumption safe.
