# P3 specs

Every spec follows `docs/p3/EXECUTION-PLAN.md` §0.5. An executor reads plan §0.3, §2, §3 and **one** spec.

| Spec | Title | Wave | Depends on | h | Status (6 Nov) |
|---|---|---|---|---|---|
| [SPEC-01](SPEC-01-foundation.md) | Foundation: ports, AsyncCore, frames, fake core, fake room | 0 | none | 1.5 | Merged #11 |
| [SPEC-02](SPEC-02-grammar.md) | Grammar parser | 1 | 01 | 1 | Merged #15 |
| [SPEC-03](SPEC-03-identity.md) | Identity and `people.yaml` | 1 | 01 | 0.5 | Merged #13 |
| [SPEC-04](SPEC-04-errors.md) | Errors people can act on | 1 | 01 | 0.5 | Merged #12 |
| [SPEC-05](SPEC-05-messages.md) | Message templates | 1 | 01 | 1.5 | Merged #16 |
| [SPEC-06](SPEC-06-settings-events.md) | Settings and event decoding | 1 | 01 | 1 | Merged #14 |
| [SPEC-07](SPEC-07-connection.md) | Agent connection and fake Switch | 1 | 01 | 2 | Merged #17 |
| [SPEC-09](SPEC-09-register.md) | Agent registration CLI | 1 | 06 | 1 | Merged #19 (addressing fix: 09B) |
| [SPEC-09B](SPEC-09B-addressing-fix.md) | Addressing set with another agent's key | any | 09 | 0.5 | **Ready** |
| [SPEC-08](SPEC-08-ops.md) | Ops client | 2 | 06 | 1.5 | **Ready.** Values from the `switch-ops.json` schemas; live check (§8) after merge |
| [SPEC-10](SPEC-10-dispatcher.md) | Dispatcher and worker lanes | 2 | 01, 02, 06 | 1 | Merged #20 |
| [SPEC-11](SPEC-11-router-attachments.md) | Router and attachments | 2 | 01, 02, 06 | 1 | Merged #18 |
| [SPEC-16](SPEC-16-makefile-doctor-reset.md) | Makefile, doctor, local reset | 2 | 03, 06 | 1.5 | Merged #22 |
| [SPEC-16B](SPEC-16B-room-reset.md) | Room reset (archive, recreate) | 2–3 | 08, 16 | 0.75 | **Ready** once 08 merges |
| [SPEC-12](SPEC-12-close-flow.md) | Close flow and gap roots | 3 | 01, 05 | 2 | Merged #21 |
| [SPEC-13](SPEC-13-resolution-publish.md) | Resolution, publish, reports, ask | 3 | 04, 11, 12 | 2 | Merged #24 |
| [SPEC-14](SPEC-14-hygiene.md) | Resume, notices, noise guard, board | 3 | 12 | 1.5 | Merged #23 |
| [SPEC-15](SPEC-15-app-runner.md) | App wiring, runner, end-to-end loop | 4 | 02–14, 08 | 2 | **Ready** once 08 merges |
| [SPEC-17](SPEC-17-readme.md) | README, setup docs, needs-room test | 5 | 15, 16 | 1 | **Ready** once 15 merges (M2 parts marked TODO) |
| [SPEC-18](SPEC-18-real-core.md) | Real-core integration | 5 | P2 core, `data/seed/EXPECTED.md` | 2 | **Blocked:** P2 PRs #8–#10 open; no `EXPECTED.md` |

**Next to run:** SPEC-08 and SPEC-09B in parallel. Then SPEC-15 and SPEC-16B. Then SPEC-17.

## Where these specs change the plan
Each change is also recorded in the spec named. Plan §3 was edited where it is binding.
- **SPEC-01:** `frame_kind` prefers a domain kind in `data.type` (plan §3.2). FakeCore gains `keep_open` and
  `audit` hooks (§3.16). `FakeRoom.link` gives `"message m-3"`. Fake `ingest_file` skips the close check (rule
  17).
- **SPEC-05:** all copy is pinned. New template `old_close_gap` (§3.9). Blank lines between Markdown blocks.
- **SPEC-07:** the cursor from `connection_state` is used only when there is none yet, and `gap` sets
  `resumed_at - 1`. Both avoid losing events.
- **SPEC-08:** op argument names are module constants taken from the schemas. `OpsClient` gains `agent_ids` and
  `connect_room()` (§3.11). `read_context` is flattened from threads, and documents are updated by id.
- **SPEC-09B:** `update_agent_detail` refuses the caller itself, so carbon-room sets the others and collector sets
  carbon-room.
- **SPEC-13:** a reply in a thread from an older close is refused (`resolve` always acts on the latest close).
- **SPEC-15:** `amain` returns an exit code, and `Runtime` has `start`, `wait_connected` and `stop`.
- **SPEC-16:** split. The room part is SPEC-16B, which recreates the room with `create_room(agent_names=…)` under
  the archived room's name.

## Live checks still owed (M2)
`scripts/spikes/m2_ops_check.py` covers S1, S5 and S6, plus addressing. It posts into the room in `.env`, so run
it yourself with `make run` stopped. S2 (attachment download), S3 (two humans) and S4 (four sockets under load)
remain manual; see plan §6 M2.

## Executor prompt (Sonnet, one spec, fresh worktree)
```
You are implementing one spec in the Carbon Room repo. You have no other context. Read docs/p3/EXECUTION-PLAN.md
§0.3, §2 and §3, then docs/p3/specs/<SPEC FILE> in full, then only the files its §2 lists.
Follow plan §0.3 exactly: write every test in the spec's §6 plus interface stubs that raise NotImplementedError,
run pytest and confirm the new tests fail for the right reason, commit "test(p3-sNN): failing tests for <title>";
then implement without touching any file under tests/, commit "feat(p3-sNN): <title>"; run the checks; open the
PR with the title and body from plan §0.2.
If a test in the spec looks wrong, or the spec says BLOCKED / has a TBD, stop and report instead of guessing. Do not
edit a test in the green commit, even to fix lint; report it and let the user decide.
```
