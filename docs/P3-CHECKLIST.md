# P3 checklist — Switch room, demo and submission

This is the progress tracker. The detail for every line, including what to build, how and which tests, is in
[docs/p3/EXECUTION-PLAN.md](p3/EXECUTION-PLAN.md). Spec ids (S01…) are plan §5 and manual tracks (M1…) are
plan §6. Story ids in brackets refer to [P3-switch-room-and-demo.md](../P3-switch-room-and-demo.md).

Tick a line on `main` after its PR merges. Feature PRs don't edit this file.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · (cut) = drop first if late.

**Deadlines:** README reproducible by Fri 6 Nov 12:00 PT · freeze Fri 6 Nov 17:00 PT · submit Sat 7 Nov 10:00 PT

## Blocked on teammates (plan §1.3–§1.4)

- [ ] **P2:** `config/carbon_room.yaml` and `config/factors.csv` on `main`. `start_close` fails without the yaml.
- [ ] **P2:** `calculate`, `check`, `resolve`, `summary`, `draft_report`, `publish` and `trace` in
      `carbon_room.core`. The `feat/calc-check` branch is the old `carbonroom` package and has to be ported.
- [ ] **P2:** answer plan §1.4: one Warehouse-2 gap or two; whether R6 becomes a gap; the `Report.gaps` shape;
      the publish file names; how `resolve` picks its close.
- [ ] **P1:** baseline claims are stamped with the close month, which breaks R5, Tier 1 and totals and causes
      false R2 conflicts.
- [ ] **P1:** diesel claims get `scope "2"` instead of `"1"`.
- [ ] **P1:** `ruff check .` fails on `main` with 183 errors.
- [ ] **P1 + P2:** the replay cache under `data/cache/` is gitignored, but `llm.mode: replay` needs it. Commit
      the cache or ship `mode: rules`.
- [ ] **P1 + P2:** `data/seed/EXPECTED.md`.

## Setup

- [ ] PR-0: commit `00-CONTRACTS.md`, `P3-switch-room-and-demo.md`, `Carbon Room Architecture.html`, this
      checklist and the plan (plan §0.2).
- [x] M1 Switch server, `emissions-reporting` room, four agents registered, keys in `.env` (1.1). Setup notes for `docs/setup-switch.md` still to write.
- [ ] Log in as akshar / richa and confirm both can post in `emissions-reporting` (spike S3)

## Wave 0

- [ ] S01 Foundation: ports, AsyncCore, frames, fake core, fake room (8.1)

## Wave 1 (parallel)

- [ ] S02 Grammar parser (3.1)
- [ ] S03 Identity + `people.yaml` (3.2, 1.9 template)
- [ ] S04 Actionable errors (3.5)
- [ ] S05 Message templates (5.1)
- [ ] S06 Settings + event decoding (2.2)
- [ ] S07 Agent connection + fake Switch server (2.1, 8.2)
- [ ] S09 Agent registration (1.2), after S06 merges
- [ ] M2 Spikes S1–S6, spike summary to the team, route check (1.3–1.8, 1.10)

## Wave 2 (parallel)

- [ ] S08 Ops client (2.3), after M2
- [ ] S10 Dispatcher + worker lanes (2.4)
- [ ] S11 Router + attachments (3.3, 3.4, 2.6)
- [ ] S16 Makefile, doctor, reset-demo (6.1–6.3)
- [ ] M3 Real sender ids in `people.yaml` (1.9)

## Wave 3

- [ ] S12 Close flow: orchestrator + gap roots (4.1–4.4)
- [ ] S13 Resolution, publish, reports, ask (4.5, 4.6, 5.4)
- [ ] S14 Resume, budget notices (cut), noise guard, Close Board (cut) (4.7, 4.8, 5.3, 5.2)

## Wave 4

- [ ] S15 App wiring, SwitchRoom, runner, end-to-end loop (2.5, 8.2)

## Wave 5 and finish

- [ ] S17 README, setup docs, needs-room test (6.4)
- [ ] S18 Real-core integration (4.5 and 5.2 against the real core), once P2 lands
- [ ] M4 Demo script (7.1)
- [ ] M5 Two timed rehearsals at or under 90 s (7.2)
- [ ] M6 Clean-machine run by a teammate, by Fri 12:00 PT (6.5)
- [ ] M7 Video + uncut fallback recording from the same run, by Fri 17:00 PT (7.3)
- [ ] M8 Repo public, tag `v1.0-submission`, submit by Sat 10:00 PT (7.4)
