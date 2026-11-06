# SPEC-18 · Real-core integration
Stories: the real-core "Done when" of P3-4.5 and P3-5.2; feeds P3-7.1 · Branch: `p3-s18-real-core` · PR title: "P3-S18 (4.5, 5.2): real-core integration"
Depends on (must be merged): SPEC-12, SPEC-13, SPEC-14; **P2's `calculate`, `check`, `resolve`, `summary`,
`draft_report` and `publish` on `main`**; `config/carbon_room.yaml` and `config/factors.csv`; `data/seed/EXPECTED.md`
· Wave: 5 · Estimated session time: 2 h

> **BLOCKED until §0 is filled in from `data/seed/EXPECTED.md`** and P2's core has landed. Re-read P2's answers to
> plan §1.4 before execution and record them in §11. **Executor: if any `TBD` is left, stop and report.**

## 0. Inputs from `EXPECTED.md` and P2

| Item | Value |
|---|---|
| Open gaps after the first check: rule · kind · owner for each, in gap-number order | `TBD` |
| Is Warehouse-2's R1 and R4 one gap or two? | `TBD` |
| Does R6 open a gap? | `TBD` |
| `summary` after check: verified kg, excluded kg, coverage %, sources verified | `TBD` |
| After the Warehouse-2 upload | `TBD` |
| After diesel `pick A` | `TBD` |
| After stale-factor `approve` | `TBD` |
| After variance `approve` | `TBD` |
| Option keys per rule, if they differ from contracts §6 | `TBD` |
| Files `publish` writes under `out/<month>/v<n>/` | `TBD` |

## 1. Goal
Run the room's close and resolution handlers against the **real** `carbon_room.core`, in a temp copy of the repo
data, and check that the figures after each scripted resolution match `EXPECTED.md`. Every mismatch becomes
either a room fix (a new small PR) or a message to P2.

## 2. Read before starting
- `data/seed/EXPECTED.md`
- P2's public functions in `carbon_room/calc`, `carbon_room/checks` and `carbon_room/report`, and their docstrings
- `tests/fakes/fake_core.py` and `docs/p3/EXECUTION-PLAN.md` §3.16
- `carbon_room/agents/{orchestrator,resolution,publish}.py` and `carbon_room/room/board.py`

## 3. Files
- Create `tests/room/test_real_core_flow.py`
- Modify `tests/fakes/fake_core.py` **only** to mirror the real core's **structure**: option keys, the number of
  gaps, which rules open gaps, and gap order. Titles, labels, evidence and numbers stay fake, so the SPEC-05,
  SPEC-12 and SPEC-13 snapshot tests don't change. If a structural change breaks an existing test, list each
  changed test under Deviations, with the reason.

## 4. Public interface
None new.

## 5. Behaviour
1. **Skip conditions.** At import time, the module calls `pytest.skip(..., allow_module_level=True)` with reason
   `"P2 core not merged"` when `core.calculate` raises `NotImplementedError` on a probe. The probe is
   `inspect.getsource(core.calculate)` containing `_unimplemented`. When `data/seed/EXPECTED.md` is missing, it
   skips with `"EXPECTED.md missing"`.
2. **Sandbox.**
   1. Copy `config/`, `data/seed/` and `data/demo_uploads/` into `tmp_path` and `monkeypatch.chdir(tmp_path)`.
   2. Set `CARBON_ROOM_CONFIG_DIR=tmp_path/config` and `config.clear_caches()`. The people come from
      `tests/room/fixtures/people.yaml`, copied over `config/people.yaml`.
   3. Run `python -m carbon_room init` (subprocess, `cwd=tmp_path`).
   4. Load factors the way P2 documents. Record the call in this spec's §11 when filling §0.
3. **Room.** `ctx = Context(core=AsyncCore(carbon_room.core, executor), room=NoiseGuard(FakeRoom(), max_posts=12),
   display=lambda pid: f"@{pid}", today=lambda: date(2026, 11, 5), inbox_dir=Path("data/inbox"))`, with
   `ctx.on_phase_end = partial(hooks.after_phase, ctx)`.
4. **Flow.** `handle_close_start` with `LEAD` and message `h-1`. Then, through `handle_gap_reply`, each in the gap
   thread found by **rule and kind**, not by `G-n`:
   1. Copy the demo upload into `data/inbox/`, then Priya replies `upload warehouse2_electricity_2026-10_actual.pdf`
   2. The Lead replies `pick A` on the R2 gap
   3. The Lead replies `approve` on the R3 gap
   4. The Lead replies `approve` on the R5 gap
5. **Assertions.** After the check and after each step, `await ctx.core.summary(cid)` equals the §0 row (verified,
   excluded, coverage and sources verified, exactly as Decimal). Also:
   - the top-level post count is at most 12
   - after each step, the `close-board` document equals `board(...)` of that summary
   - every gap thread got `Checking…` followed by an outcome
6. **Publish.** `handle_draft` then `handle_publish` (LEAD) succeed. The published post lists the §0 files.

## 6. Test plan
| Test | Assert |
|---|---|
| `test_real_close_opens_expected_gaps` | the rule, kind and owner list equals §0 row 1 |
| `test_real_resolutions_match_expected` | the five summary snapshots equal §0, in order |
| `test_real_flow_noise_and_board` | top-level ≤ 12; the board equals `summary()` after each step |
| `test_real_publish_lists_files` | the published text has `Files:` with the §0 files |
| `test_real_ask_unknown_then_verified` | before the upload, `@collector what is Warehouse-2 October electricity?` contains `UNKNOWN` and `priya`; after it, it contains `Verified ledger facts:` |

## 7. Fixtures and doubles
`FakeRoom`, `NoiseGuard` and the real core. No `FakeCore` in this module.

## 8. Manual check
This test is the dress rehearsal for M5: run it, then `make reset-demo` and do the same in the real room.

## 9. Done when
- [ ] Against the real core, the four scripted resolutions from `EXPECTED.md` move the total to the expected figure
- [ ] Every test in §6 passes (not skipped), and the full `pytest -q` passes
- [ ] ruff passes on `tests/room tests/fakes`

## 10. Not in this spec
Fixing P2's code. Report mismatches to P2 with the failing snapshot.

## 11. Open questions
1. **Blocking:** §0, which depends on P2 and on `EXPECTED.md`.
2. How factors are loaded before a close (P1 handoff: P2 loads immutable factor rows). Record the call here.
3. Plan §1.3 P1 defects 1 and 2 (baseline month stamping, diesel scope) will show up here as wrong totals. Check
   that they are fixed on `main` before filling §0.
