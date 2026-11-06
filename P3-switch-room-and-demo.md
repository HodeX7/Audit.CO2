# P3 — Switch Room, Demo & Submission

**You own everything a judge sees and everything that makes Switch load-bearing.** That is the Switch and Mattermost setup, agent registration, the Python room client on Switch's agent protocol, the router, the orchestrator, the room messages, the Close Board, the Makefile and README, the clean-machine run, the demo video and the submission. Switch is 30% of the score and README plus reproducibility is 45%, so this file covers most of the marks.

Contracts live in [00-CONTRACTS.md](00-CONTRACTS.md). Each story below says which sections to read. You own §8 and `people.yaml` in §9. **You never import `carbon_room.ledger`; you only call `carbon_room.core` (§4).**

## What you consume from others

| From | What | Needed by |
|---|---|---|
| P1 | `models.py` and `core.py` stubs (M0) | 3.x, 4.x, 8.1 |
| P1 | `start_close`, `ingest`, `gap_for_thread`, `record_gap_thread`, `resume_state`, `explain`, `budget_usage`, `verify_audit` | 4.x, 5.4 |
| P2 | Finding/Gap shape and option keys, frozen (Wed 15:00) | 3.3, 5.1 |
| P2 | `calculate`, `check`, `resolve`, `summary` (M3) | 4.3–4.5 |
| P2 | `draft_report`, `publish`, `trace` (M4) | 4.6 |
| P1 | `data/seed/EXPECTED.md` (M4) | 7.1 |

**Until the real core lands, build against the fake core (8.1).** The fake lives in `tests/` and is never on the run path.

## Story map

| Milestone (PT) | Stories |
|---|---|
| **M0 Contracts** — Wed 12:00 | 1.1, 3.1, 8.1 |
| **M1 Spikes** — Wed 18:00 | 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.3 |
| **M2 Walking skeleton** — Wed night | 2.2, 2.4, 2.5, 3.2, 3.3, 4.1, 4.3, 4.4, 5.1 (first templates) |
| **Route check** — Thu 10:00 | 1.10 |
| **M3 Traps** — Thu 14:00 | 2.6, 3.4, 3.5, 4.2, 4.5, 5.1 (all templates), 6.1, 6.2, 8.2 |
| **M4 End to end** — Thu night | 4.6, 4.7, 4.8, 5.2, 5.3, 5.4, 6.3, 7.1, 7.2 |
| **M5 Reproducible** — Fri 12:00 | 6.4, 6.5 |
| **M6 Freeze** — Fri 17:00, submit Sat 10:00 | 7.3, 7.4 |

This is the heaviest file. If P1 or P2 finish early, hand them 5.4 (ask handler), 6.4 (README draft) or 7.1 (demo script). Those stories have the fewest dependencies.

## Handing a story to an AI agent

Paste this, then the story text, and nothing else:

```
You are implementing one story in the Carbon Room repo (Python 3.11, package carbon_room).
Read ONLY: specs/00-CONTRACTS.md sections <§ list from the story>, the files listed under "Files",
and docs/switch-protocol-notes.md if the story touches Switch.
First reply with a plan of 5 lines or fewer: files you will touch, functions you will add, tests you will add.
Never import carbon_room.ledger; call carbon_room.core only. Never compute a number or a status in the room layer.
Never block the asyncio loop: core and LLM calls go through the worker pool.
Do not change any signature or type in 00-CONTRACTS.md. If you think one must change, stop and say why.
Done = every "Done when" item is true and `pytest` and `ruff check` pass.
```

---

## F1 · Switch environment and spikes

Spikes answer the questions the Switch docs leave open. Each spike ends in a short note in `docs/spikes.md`: what you tried, what happened, and pass or fail. If it fails, record the fallback you chose.

### P3-1.1 · Local Switch, Mattermost and the room
**Milestone** M0 · **Size** M · **Needs** — · **Read** §8 (agent names)
**Files:** `docs/setup-switch.md`
**Build:**
- Install Docker and Switch Console, choose "Run a server on this computer", and start it. The first start downloads several GB, so start it before anything else.
- Create the Mattermost room `october-close`.
- Create a registration key on the Gateway's API Keys page.
- Write every step with exact versions, screenshots and the time each step took. This file becomes the README setup section.
**Done when:**
- [ ] `curl <server>/health` returns healthy
- [ ] A teammate has followed `docs/setup-switch.md` on their own machine without asking you anything
**Not here:** Agents.

### P3-1.2 · Agent registration script
**Milestone** M1 · **Size** S · **Needs** 1.1 · **Read** §8 (agent names)
**Files:** `carbon_room/room/register.py`, `.env.example`, `docs/switch-protocol-notes.md`
**Build:**
- `python -m carbon_room.room.register` calls `POST /agents` with the registration key for `carbon-room`, `collector`, `watchdog` and `reporter`. Each request sends `connector_type: "carbon-room-python"`, `connection_model: "always_on"`, `message_exchange: true` and empty mediation lists.
- It writes each returned `id` and `api_key` to `.env` (shown once; never printed in logs).
- A 409 (name taken) is reported clearly and skipped.
- It then calls `update_agent_detail` on each agent with `addressing: "anyone"`.
- Start `docs/switch-protocol-notes.md` with the endpoints you actually used.
**Done when:**
- [ ] Running it twice is safe
- [ ] All four agents appear as participants in the room after `invite_agent_to_room`
**Not here:** Connecting.

### P3-1.3 · Spike S1 + S5: posting, threads and message ids
**Milestone** M1 · **Size** S · **Needs** 1.2 · **Read** —
**Files:** `scripts/spikes/s1_threads.py`, `docs/spikes.md`, `docs/switch-ops.json`
**Build:**
- Save the output of `GET /agents/{id}/ops` to `docs/switch-ops.json`.
- Find `post_message`'s input schema. Is there a thread or parent parameter? Does the result return the new message id?
- Post a root message, then a reply into its thread. Check in Mattermost that the reply is threaded.
- Check that a human reply in that thread arrives as an event with a `thread_id` equal to the root id.
**Done when:**
- [ ] `docs/spikes.md` records pass or fail for S1 and S5. Fallbacks if they fail: S1 → `G-2 pick A` in the channel (3.4); S5 → `read_context` after posting
**Not here:** —

### P3-1.4 · Spike S2: attachments
**Milestone** M1 · **Size** S · **Needs** 1.2 · **Read** §6 (upload)
**Files:** `scripts/spikes/s2_attachments.py`, `docs/spikes.md`
**Build:** Attach a PDF in the room. Log the event's `attachments` entry (filename, mimetype, size, mxc). Try to download the bytes through the media routes, and compare the SHA with the original.
**Done when:**
- [ ] Pass: SHA matches. Fail: record the fallback — the person attaches for the record, the file is placed in `data/inbox/`, and the reply names it. The README says this plainly
**Not here:** —

### P3-1.5 · Spike S3: more than one human
**Milestone** M1 · **Size** S · **Needs** 1.1 · **Read** §9 (`people.yaml`)
**Files:** `docs/spikes.md`
**Build:** In the bundled Mattermost, create users `lead` and `priya`. Log in as each in two browser profiles. Post as each, and record each sender id as the agent sees it.
**Done when:**
- [ ] Pass: two distinct sender ids recorded. Fail: one account; `people.yaml` maps it to `lead`, and the demo narrates Priya's step. README says so
**Not here:** —

### P3-1.6 · Spike S4: four sockets under load
**Milestone** M1 · **Size** S · **Needs** 2.1 · **Read** —
**Files:** `scripts/spikes/s4_four_sockets.py`, `docs/spikes.md`
**Build:** One process opens four sockets, one per agent key. A worker thread runs `time.sleep(10)` (standing in for an LLM call) while the loop keeps answering pings. Run it for 2 minutes.
**Done when:**
- [ ] Pass: no `evicted` frames in 2 minutes. Fail: fall back to one visible agent (`carbon-room`) posting with `[Watchdog]`, `[Collector]` and `[Reporter]` prefixes
**Not here:** —

### P3-1.7 · Spike S6: room documents
**Milestone** M1 · **Size** S · **Needs** 2.3 · **Read** —
**Files:** `docs/spikes.md`
**Build:** `create_room_document` named `close-board` with some Markdown, then `update_room_document`. Is it visible to a person in Mattermost, in Switch Console, or neither?
**Done when:**
- [ ] Pass or fail recorded. If it fails: the Close Board is a normal post at the end of each phase (5.2)
**Not here:** —

### P3-1.8 · Spike summary to the team
**Milestone** M1 · **Size** S · **Needs** 1.3–1.7 · **Read** —
**Files:** `docs/spikes.md`
**Build:** A table of S1–S6 with pass or fail, the chosen path, and the stories affected. Post it in the team chat by 18:00.
**Done when:**
- [ ] P1 and P2 have acknowledged it
**Not here:** —

### P3-1.9 · Fill in `people.yaml`
**Milestone** M1 · **Size** S · **Needs** 1.5 · **Read** §9 (`people.yaml`)
**Files:** `config/people.yaml`
**Build:** Enter the real sender ids from spike S3. Roles: `lead` → lead, `priya` → site_manager for `warehouse-2`. Finance and auditor are optional.
**Done when:**
- [ ] Every human in the demo has a role
**Not here:** —

### P3-1.10 · Route check
**Milestone** Thu 10:00 · **Size** S · **Needs** 2.5, 4.3 · **Read** —
**Files:** `docs/spikes.md`
**Build:** Can the direct client post a gap thread, receive a human reply in it, and call the core? If not, switch to the fallback: Claude Code as the room agent (supported by Switch out of the box), with `core.py` exposed as MCP tools through `carbon_room/room/mcp_server.py`. That fallback would be its own set of stories, written only if the check fails.
**Done when:**
- [ ] The decision is recorded and announced to the team
**Not here:** —

---

## F2 · Room client (the Switch agent protocol)

Every endpoint and field name used here goes into `docs/switch-protocol-notes.md` as you confirm it. The Switch docs say there is no client library.

### P3-2.1 · Connect, heartbeat, reconnect
**Milestone** M1 · **Size** M · **Needs** 1.2 · **Read** —
**Files:** `carbon_room/room/connection.py`, `tests/room/test_connection.py`
**Build:** `AgentConnection(agent_name, agent_id, api_key, server, room_id, filter)`:
- Open `GET /agents/{id}/connection/ws?connection_id=<uuid>&rooms=<room>&filter=<filter>` with `Authorization: Bearer`.
- Read the first `connection_state` frame.
- **Answer every `ping` with `{"type":"pong","cursor":<highest sequence>}` straight from the read loop.**
- Track the highest `sequence`.
- On disconnect, reconnect with the same `connection_id` and `start_from=<cursor>`, with backoff of 1, 2, 4 seconds and a 30-second cap.
- On `evicted`, log the reason and code, then reconnect.
- Hand domain events to an async callback. The callback must never be awaited inline for long; it puts the event on a queue.
**Done when:**
- [ ] Against the fake Switch server (8.2): pongs are sent within 200 ms, and a server-side close leads to a reconnect without lost events
**Not here:** Parsing events (2.2).

### P3-2.2 · Event decoding
**Milestone** M2 · **Size** S · **Needs** 2.1 · **Read** —
**Files:** `carbon_room/room/events.py`, `tests/room/test_events.py`
**Build:** A `RoomEvent` dataclass with `type`, `room_id`, `message_id`, `thread_id`, `sender`, `sender_name`, `body`, `attachments`, `addressed`, `timestamp`, `receiving_agent`. Write `decode(frame, receiving_agent)`. Drop events whose sender is one of our own four agents, so the agents never react to themselves.
**Done when:**
- [ ] Fixtures for `message`, `command`, `room_join` and a control frame each decode or are skipped correctly
**Not here:** —

### P3-2.3 · Ops caller and posting helpers
**Milestone** M1 · **Size** M · **Needs** 1.3 · **Read** —
**Files:** `carbon_room/room/ops.py`, `tests/room/test_ops.py`
**Build:** An async `httpx` client:
- `call(op, args)` sends `POST /agents/{id}/ops/{op}` with the `X-Switch-Connection-Id` header and returns `result`. A 400 raises an error that shows the server's detail.
- Helpers: `post(text, thread_id=None) -> message_id` (shaped by the spike S1/S5 results), `send_targeted(to_agent, text)`, `read_context(limit)`, `upsert_room_doc(name, content)`.
**Done when:**
- [ ] Unit tests with a mocked transport check the headers, the body and how errors are mapped
**Not here:** —

### P3-2.4 · Queue and worker pool
**Milestone** M2 · **Size** M · **Needs** 2.1 · **Read** §4
**Files:** `carbon_room/room/dispatch.py`, `tests/room/test_dispatch.py`
**Build:**
- One `asyncio.Queue` for incoming events.
- Handlers run core calls in a `ThreadPoolExecutor` via `run_in_executor`.
- **Calls for the same close run one at a time** (one lock per close), so two human replies can't race.
- A handler exception is caught, logged and turned into a friendly room reply (3.5).
**Done when:**
- [ ] A test: a 5-second fake core call doesn't delay a pong
- [ ] Two resolves for the same close run in order
**Not here:** —

### P3-2.5 · Multi-agent runner
**Milestone** M2 · **Size** S · **Needs** 2.1–2.4 · **Read** §8 (agent names)
**Files:** `carbon_room/room/run.py`
**Build:**
- `python -m carbon_room.room.run` loads `.env`, opens four `AgentConnection`s and wires them into one dispatcher.
- Filters: `watchdog` uses `filter=all` so it sees thread replies; the others use `addressed`.
- `Ctrl-C` shuts down cleanly.
- At startup, log one line per agent: connected, room, filter.
**Done when:**
- [ ] `make run` shows four connected agents, and a message to `@carbon-room` is received by that agent only
**Not here:** —

### P3-2.6 · Attachment fetch
**Milestone** M3 · **Size** S · **Needs** 1.4, 2.3 · **Read** §6 (upload)
**Files:** `carbon_room/room/attachments.py`, `tests/room/test_attachments.py`
**Build:**
- If S2 passed: download the attachment to `data/inbox/<message_id>_<filename>` and return the path.
- If S2 failed: look for `data/inbox/<filename>` by the attachment's filename, or by the name typed after `upload`.
- Either way, the path goes to `resolve` as `payload["path"]`.
**Done when:**
- [ ] Both paths are tested. On the fallback path, a missing file gives the reply "I can't see that file yet. Put it in data/inbox/ and reply upload <name>."
**Not here:** —

---

## F3 · Router

Turns a `RoomEvent` into an `Intent` and an `Actor`. Pure functions, many tests, no network.

### P3-3.1 · Grammar parser
**Milestone** M0 · **Size** M · **Needs** — · **Read** §8
**Files:** `carbon_room/room/grammar.py`, `tests/room/test_grammar.py`
**Build:** `parse(body, receiving_agent, in_thread: bool) -> Intent`, where `Intent = {kind, args, target_agent}`, with every row of §8 as a case:
- Month names in any case, with an optional year (defaults to the current close year).
- `S-14` is read as `S-014`.
- Anything else addressed to an agent is `ask`.

At least 25 table-driven test cases, including near-misses ("pick a" means `pick A`; "approved" counts as `approve`).
**Done when:**
- [ ] Every row of §8 has at least one passing case, and an unknown command gives `ask`
**Not here:** Identity or gaps.

### P3-3.2 · Identity
**Milestone** M2 · **Size** S · **Needs** 1.9 · **Read** §2 (`Actor`), §9 (`people.yaml`)
**Files:** `carbon_room/room/identity.py`, `tests/room/test_identity.py`
**Build:** `actor_for(sender_id, sender_name) -> Actor`, using `load_people()`. Unknown senders become `Actor(kind="human", id="guest:<sender>", role=None)`. Our own agents map to `Actor(kind="agent", id=<name>)`.
**Done when:**
- [ ] Known, guest and agent cases are tested
**Not here:** Permission checks. P2's `resolve` and `publish` enforce roles; the room only passes the actor along.

### P3-3.3 · Thread replies to gap options
**Milestone** M2 · **Size** S · **Needs** 3.1 · **Read** §6, §8, §4 (`gap_for_thread`)
**Files:** `carbon_room/room/router.py`, `tests/room/test_router.py`
**Build:**
- For a message with a `thread_id`, call `core.gap_for_thread(thread_id)`. No gap means ignore it, unless the message is addressed to an agent.
- Match the body to one of the gap's `options[].key`, ignoring case and allowing a trailing reason after `reject`.
- An attachment counts as `upload`.
- No match: reply in the thread with the valid keys.
**Done when:**
- [ ] "Pick a" in the diesel thread gives `resolve(G-2, "pick", ...)` with option A's params
- [ ] "hello" in a gap thread gets a reply listing the options
**Not here:** —

### P3-3.4 · Fallback `G-n` syntax
**Milestone** M3 · **Size** S · **Needs** 3.3 · **Read** §8 (fallback row)
**Files:** `carbon_room/room/router.py`, `tests/room/test_router.py`
**Build:** `G-2 pick A` anywhere in the room routes the same way as a thread reply. Always on, even if S1 passed, so a judge can use either.
**Done when:**
- [ ] It is tested with and without a thread
**Not here:** —

### P3-3.5 · Errors people can act on
**Milestone** M3 · **Size** S · **Needs** 2.4 · **Read** §2 (exceptions)
**Files:** `carbon_room/room/errors.py`, `tests/room/test_errors.py`
**Build:** Map each exception to a short reply that says what to do:
- `NotAllowed` → "Only the Lead or the gap owner (Priya) can do that."
- `NeedsRoomEvent` → shouldn't happen from the room; log it as a bug.
- `LockHeld` → "@collector is still reading that source. Try again in a moment."
- `BudgetExceeded` → "<agent> has hit its budget for this close and has stopped. The Lead can raise it in config."
- Anything else → "Something went wrong on my side (error id). The ledger is unchanged."
**Done when:**
- [ ] Every exception type in §2 has a tested message
**Not here:** —

---

## F4 · Orchestrator and close flow

**Lever:** the orchestrator is a LangGraph `StateGraph`, and the **ledger is the authoritative state**. If waiting for agent hand-offs with LangGraph interrupts costs more than 2 hours, call the core in-process and post as each agent instead. The room looks the same, and the README describes what was built.

### P3-4.1 · Close graph skeleton
**Milestone** M2 · **Size** M · **Needs** 2.5, 8.1 · **Read** §4, §7 (phases)
**Files:** `carbon_room/agents/orchestrator.py`, `tests/room/test_orchestrator.py`
**Build:** A graph with nodes `plan → collect → calculate → check → post_gaps → await_humans`, using `MemorySaver` keyed by `close_id`. Each node calls one core function through the dispatcher and posts as the right agent. `await_humans` ends the run. Later events re-enter through 4.5.
**Done when:**
- [ ] Against the fake core: `close October` posts the plan, the collector statement, the gap roots and a summary, in order
**Not here:** Message wording (5.1).

### P3-4.2 · Visible hand-offs between agents
**Milestone** M3 · **Size** S · **Needs** 4.1, 1.6 · **Read** §8 (agent names)
**Files:** `carbon_room/agents/orchestrator.py`
**Build:** Before each delegated step, `@carbon-room` sends a targeted message (`send_targeted("collector", "Collect October for hq, warehouse-2, dc-eu-west")`). The receiving agent posts its own result. Judges should see agents passing work, not one bot talking.
**Done when:**
- [ ] The room shows three distinct agent names posting during one close
**Not here:** —

### P3-4.3 · Post gaps as threads
**Milestone** M2 · **Size** S · **Needs** 4.1, 2.3 · **Read** §2 (`Gap`), §4 (`record_gap_thread`), §6
**Files:** `carbon_room/agents/gaps.py`
**Build:**
- For each OPEN gap with no `thread_root_message_id`: `@watchdog` posts the gap root (5.1 template) and calls `core.record_gap_thread`.
- One post per gap, ever, so re-checks never repost.
- Mention the owner by Mattermost username when spike S3 passed.
**Done when:**
- [ ] Running `check` twice posts each gap root once
**Not here:** —

### P3-4.4 · The refusal and the summary
**Milestone** M2 · **Size** S · **Needs** 4.3 · **Read** §2 (`CloseSummary`), §7 (Totals)
**Files:** `carbon_room/agents/orchestrator.py`
**Build:** After the gap roots, `@carbon-room` posts the refusal: "I can't give a clean October total yet." It then gives the verified figure, the excluded figure, coverage, `source_coverage` and the number of open gaps with owners. **Every number comes from `summary()`; none is computed here.**
**Done when:**
- [ ] The post's numbers equal `summary()` output in a test
**Not here:** —

### P3-4.5 · Resolution loop
**Milestone** M3 · **Size** M · **Needs** 3.3, 4.3, 4.4 · **Read** §4 (`resolve`), §6
**Files:** `carbon_room/agents/resolution.py`, `tests/room/test_resolution.py`
**Build:** On a `gap.resolve` intent:
1. `@watchdog` replies in the thread "Checking…".
2. Call `core.resolve` with the actor and the message id.
3. Reply in the thread with the outcome (resolved, still open and why, or the error).
4. Post any new gaps (4.3).
5. If the verified total changed, `@carbon-room` posts **one** top-level line: "Total moved X → Y tCO2e, coverage A% → B%."
**Done when:**
- [ ] Against the real core in replay mode, the four scripted resolutions from EXPECTED.md move the total to the expected figure
- [ ] An unchanged total posts no top-level line
**Not here:** —

### P3-4.6 · Draft and publish
**Milestone** M4 · **Size** S · **Needs** 4.5 · **Read** §4 (`draft_report`, `publish`), §8
**Files:** `carbon_room/agents/publish.py`
**Build:**
- `@reporter draft` → post the headline, the excluded and gap lists, the DC line and the compliance flags.
- `@carbon-room publish` → `core.publish(actor, message_id)`, then post "Published v1 by <name>" with the output paths.
- Use the errors from 3.5 when someone without the right role tries.
**Done when:**
- [ ] A lead can publish and a guest gets a clear refusal
**Not here:** —

### P3-4.7 · Resume after a crash
**Milestone** M4 · **Size** S · **Needs** 4.3 · **Read** §4 (`resume_state`)
**Files:** `carbon_room/agents/orchestrator.py`
**Build:** `@carbon-room resume` (and automatically at startup if the latest close is not PUBLISHED): read `resume_state`, post "Resuming October close at <phase>", and repost a short list of open gaps with links to their existing threads. Never repost a root.
**Done when:**
- [ ] Kill the runner mid-close, restart it, and the room shows the resume line with the right gaps
**Not here:** —

### P3-4.8 · Budget and lock notices
**Milestone** M4 · **Size** S · **Needs** 2.4 · **Read** §4 (`budget_usage`)
**Files:** `carbon_room/agents/notices.py`
**Build:** After each phase, call `core.budget_usage`. Post once per agent at `warn` ("@collector has used 80% of its budget for this close") and once at `stopped`.
**Done when:**
- [ ] With a tiny test budget, the warning appears once and not again
**Not here:** —

---

## F5 · Room experience

### P3-5.1 · Message templates
**Milestone** M2 (plan, gap root, summary), M3 (all) · **Size** M · **Needs** 3.1 · **Read** §2, §6, §8
**Files:** `carbon_room/room/messages.py`, `tests/room/test_messages.py`
**Build:** One function per message:
- close plan; collector statement
- gap root: title, owner, evidence quoted exactly, then "Reply in this thread with:" and the option keys and labels
- thread outcome; refusal and summary; total moved
- draft; published
- trace card: file, page, excerpt, SHA (first 12 characters), factor and version, recompute, approver, chat message link
- audit result; UNKNOWN answer; help

Short sentences and plain words. **Templates format values; they never compute them.** Snapshot tests keep the wording stable.
**Done when:**
- [ ] Each template has a snapshot test, and the gap root for the diesel conflict shows both excerpts and both options
**Not here:** —

### P3-5.2 · Close Board
**Milestone** M4 · **Size** S · **Needs** 1.7, 4.4 · **Read** §2 (`CloseSummary`)
**Files:** `carbon_room/room/board.py`
**Build:** After every status change, `@carbon-room` upserts the room document `close-board`: coverage, verified, excluded, and a table of open gaps with owner and thread. If spike S6 failed, post a compact board message at the end of each phase instead.
**Done when:**
- [ ] The board matches `summary()` after each of the four scripted resolutions
**Not here:** —

### P3-5.3 · Noise guard
**Milestone** M4 · **Size** S · **Needs** 4.1 · **Read** §9 (`noise`)
**Files:** `carbon_room/room/noise.py`
**Build:** Count top-level posts per close. Over `max_top_level_posts`, merge non-essential posts into the next summary and log a warning. Thread replies don't count.
**Done when:**
- [ ] A full scripted close stays at or under 12 top-level posts
**Not here:** —

### P3-5.4 · Ask handler
**Milestone** M4 · **Size** S · **Needs** 3.1 · **Read** §4 (`explain`)
**Files:** `carbon_room/agents/ask.py`
**Build:** An `ask` intent to any agent calls `core.explain(close_id, question, actor)` and replies in place, as the agent that was asked.
**Done when:**
- [ ] "@collector what is Warehouse-2 October electricity?" gets UNKNOWN naming Priya before the upload, and a verified figure after
**Not here:** —

---

## F6 · Run and reproduce

Reproducibility is 25% of the score. A judge must get from clone to a running close by following the README alone.

### P3-6.1 · Makefile
**Milestone** M3 · **Size** S · **Needs** 2.5 · **Read** —
**Files:** `Makefile`
**Build:** Targets:
- `setup` (venv + install)
- `seed` (`scripts/make_seed.py`)
- `register` (1.2)
- `doctor` (6.2)
- `run` (room runner)
- `reset-demo` (6.3)
- `test`
- `refresh-cache` (live extraction, needs an API key)

Every target prints what it does.
**Done when:**
- [ ] `make setup seed doctor test` works on a fresh clone
**Not here:** —

### P3-6.2 · `make doctor`
**Milestone** M3 · **Size** S · **Needs** 1.2 · **Read** §9 (`llm.mode`)
**Files:** `carbon_room/room/doctor.py`
**Build:** Checks, each printing a tick or a cross with how to fix it:
- Docker is running
- Switch `/health` responds
- The four agent keys are in `.env`
- The room id is set
- `people.yaml` has no placeholders
- The database initialises
- The replay cache covers every seed file
- An API key is present (only required in live mode)
**Done when:**
- [ ] Each check fails with a helpful message when you break it on purpose
**Not here:** —

### P3-6.3 · `make reset-demo`
**Milestone** M4 · **Size** S · **Needs** 6.1 · **Read** —
**Files:** `scripts/reset_demo.sh`
**Build:**
- Delete `var/` (the database and store) and `data/inbox/`, then re-initialise.
- Archive the current room and create a fresh `october-close` (`archive_room` / `create_room` ops), then invite the four agents.
- The person running it must confirm before anything is deleted.
**Done when:**
- [ ] Two full rehearsals back to back start from an identical state
**Not here:** —

### P3-6.4 · README
**Milestone** M5 · **Size** M · **Needs** 6.1, 6.2, 1.8 · **Read** §8, §10
**Files:** `README.md`, `docs/architecture.png` (or a link to the architecture page)
**Build:** In this order:
1. What it is, in one paragraph.
2. **How Switch is used:** the agents connected (four, on the direct protocol), the channel setup, and **what breaks without Switch** (cite `tests/test_publish_needs_room.py`).
3. Quick start: clone → `make setup seed register doctor run`, with expected times.
4. Running the demo close, step by step, with the exact messages to type.
5. The traps and the rule that catches each.
6. What is synthetic and what is not claimed: seeded data, illustrative numbers, Wispr not integrated, no legal advice.
7. Spike results and any fallbacks used, stated plainly.
8. Architecture picture.
9. Team and track.
**Done when:**
- [ ] A teammate who didn't write it follows it to a published close without asking a question
**Not here:** —

### P3-6.5 · Clean-machine run
**Milestone** M5 · **Size** M · **Needs** 6.4 · **Read** —
**Files:** `docs/clean-machine-run.md`
**Build:** Someone other than you runs the README on a machine or user account that has never had this project. Log every snag, then fix the README or the scripts.
**Done when:**
- [ ] A clean run reaches "Published v1", and the log is committed
**Not here:** —

---

## F7 · Demo and submission

### P3-7.1 · Demo script
**Milestone** M4 · **Size** S · **Needs** P1-7.5 · **Read** §10
**Files:** `docs/demo-script.md`
**Build:** Beats with timings:
- the mess (10 s)
- the ledger builds (15 s)
- the refusal with gap threads (30 s)
- fixes in threads, with the total moving (20 s)
- the data-centre line (10 s)
- the coverage slide (5 s)

Write the exact messages typed and who types them. Quote numbers from `EXPECTED.md` only. Add one judge-question answer per beat.
**Done when:**
- [ ] Read aloud, it fits in 90 seconds
**Not here:** —

### P3-7.2 · Rehearsals
**Milestone** M4 (first), M6 (second) · **Size** S · **Needs** 7.1, 6.3 · **Read** —
**Files:** `docs/demo-script.md` (notes section)
**Build:** Run `reset-demo` and do the full demo out loud, timed. Note every stumble and fix it in the script or the code (demo-breakers only after Thursday).
**Done when:**
- [ ] Two timed runs at or under 90 s, every trap firing live
**Not here:** —

### P3-7.3 · Record the video and the fallback
**Milestone** M6 · **Size** M · **Needs** 7.2 · **Read** —
**Files:** `docs/video.md` (links), recordings kept outside the repo
**Build:**
- Record the demo video from a live run.
- From the **same** run, keep an uncut screen recording of the Mattermost room as the fallback.
- End the video on `coverage.html`.
**Done when:**
- [ ] The video and the fallback show the same gaps, the same numbers and the same room
**Not here:** —

### P3-7.4 · Submit
**Milestone** Sat 10:00 PT · **Size** S · **Needs** 7.3, 6.5 · **Read** —
**Files:** —
**Build:**
- Make the repo public and tag `v1.0-submission`.
- Submit the video link, the README link and Track 01 Best Business Workflow on the form.
- Optional: the #HowISwitch post, and a blog post for Best Blog.
- Submit by 10:00 PT, giving 29 minutes of buffer.
**Done when:**
- [ ] The confirmation is saved in the team chat
**Not here:** —

---

## F8 · Test doubles

### P3-8.1 · Fake core
**Milestone** M0 · **Size** S · **Needs** P1-1.2, P1-1.4 · **Read** §2, §4
**Files:** `tests/fakes/fake_core.py`
**Build:** Same function names and signatures as §4. Returns fixed `Finding`, `Gap` and `CloseSummary` objects that mirror §10's traps, with an in-memory gap table so `resolve` changes the summary. **Only under `tests/`**; the runner refuses to import it.
**Done when:**
- [ ] `test_core_signatures` passes against the fake too
**Not here:** —

### P3-8.2 · Fake Switch server
**Milestone** M3 · **Size** M · **Needs** 2.1 · **Read** —
**Files:** `tests/fakes/fake_switch.py`, `tests/room/test_room_loop.py`
**Build:**
- A small `websockets` server that sends a `connection_state` frame, sends `ping` every 2 s, and evicts a connection after 6 s of silence.
- It can inject message events and records ops calls (served by a tiny HTTP handler or a mocked transport).
- The end-to-end test runs: a close command, then a thread reply, then a resolve call made, then a reply posted.
**Done when:**
- [ ] The loop test passes in CI time (under 20 s) with no real Switch
**Not here:** —
