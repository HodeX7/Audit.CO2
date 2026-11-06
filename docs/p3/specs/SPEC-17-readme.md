# SPEC-17 · README, setup docs and the needs-room test
Stories: P3-6.4, P3-1.1 (documentation) · Branch: `p3-s17-readme` · PR title: "P3-S17 (6.4, 1.1): README, setup docs and needs-room test"
Depends on (must be merged): SPEC-15, SPEC-16 · Wave: 5 · Estimated session time: 1 h

> **M1 and M2 status (6 Nov).**
> - **M1 is done in practice.** The local server answers `/health`, and `.env` has the server, the registration
>   key, the room id and all four agents. But `docs/setup-switch.md` was never written.
> - **M2 has not run.** `docs/spikes.md` still says "not run".
>
> So write both documents now, against what's known, and mark the unknowns with `<!-- TODO(M1): … -->` or
> `<!-- TODO(M2): … -->` comments:
> - `docs/setup-switch.md`: build the numbered steps from plan §6 M1, `make register` and `make doctor`. Leave
>   `<!-- TODO(M1): version, time -->` where a version or timing is needed.
> - "Spike results and fallbacks": copy the table as it is ("not run"). Then state the defaults in use
>   (`CARBON_ROOM_THREADS=1`, `CARBON_ROOM_ATTACHMENTS=inbox`, `CARBON_ROOM_SINGLE_AGENT=0`) and that each will
>   be confirmed live.
>
> The tests in §6 don't depend on spike results.

**Deadline:** the README must be complete and reproducible by **Fri 6 Nov 12:00 PT**. M6, the clean-machine
run, starts from it.

## 1. Goal
A judge goes from clone to a published close by reading the README alone. It says plainly how Switch is used,
what breaks without it (backed by a test), what is synthetic, and which spike fallbacks are in use. Tests keep the
README honest: its headings, its `make` targets and its demo commands are checked against the code.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.1, §1.5 and §2
- `00-CONTRACTS.md` §8 and §10
- `P3-switch-room-and-demo.md`, story 6.4
- `docs/setup-switch.md` (if it exists; otherwise create it), `docs/spikes.md`, `data/seed/EXPECTED.md` (if
  present; note the path is under `data/seed/`, not `docs/`),
  `Makefile`, the current `README.md`, `carbon_room/room/grammar.py` and `carbon_room/__main__.py`

## 3. Files
- Modify `README.md`: a full rewrite. Keep P1's useful content (setup notes, the data description) inside the new
  sections.
- Create or modify `docs/setup-switch.md`: numbered steps, with versions and times where known and `TODO(M1)`
  comments where not.
- Create `tests/test_publish_needs_room.py` and `tests/room/test_readme.py`.

## 4. Public interface
No code. The README structure below is the interface the tests check.

**`##` headings, exactly these, in this order:**
1. `What it is`
2. `How Switch is used`
3. `Quick start`
4. `Running the demo close`
5. `Traps and the rules that catch them`
6. `What is synthetic and what is not claimed`
7. `Spike results and fallbacks`
8. `Architecture`
9. `Team and track`

## 5. Behaviour (README content rules)
1. **What it is.** One paragraph:
   - a Switch room where a team closes a month of emissions
   - agents collect bills and build a ledger, and a rules-based Watchdog opens a thread per gap with a named owner
   - only VERIFIED rows count, and a person publishes
2. **How Switch is used.**
   - The four agents (`carbon-room`, `collector`, `watchdog`, `reporter`), each its own Switch agent on the
     direct agent protocol (WebSocket plus ops), in one Python process.
   - The room `october-close`, and the filters (watchdog `all`, the others `addressed`).
   - Targeted hand-offs between agents.
   - Gap threads, and the `G-n` fallback.
   - **What breaks without Switch:** every human state change needs a Switch `chat_message_id`, and the CLI has no
     publish, resolve or approve command. Cite `tests/test_publish_needs_room.py` by path.
3. **Quick start.**
   - Clone, then `make setup`, `make seed`, `make register`, `make doctor`, `make run`, each in a code block.
   - Give an expected time for each, from `docs/setup-switch.md`, plus the Switch Console first-start download.
   - Link `docs/setup-switch.md` for the Switch server, the room and the registration key.
4. **Running the demo close.**
   - A numbered list. Each step names who types (Lead, Priya or anyone) and the exact message in backticks.
   - Every step whose message starts with `@` or `G-` ends with an HTML comment naming the intent kind, for
     example `` 1. **Lead** types `@carbon-room close October` <!-- close.start --> ``.
   - The steps, in order:
     1. close October
     2. what to watch: the collector's statement, four gap threads, the refusal
     3. Priya attaches the real Warehouse-2 bill in its thread. Under the inbox fallback, she copies
        `data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf` into `data/inbox/` and replies
        `upload warehouse2_electricity_2026-10_actual.pdf`.
     4. the Lead replies `pick A` in the diesel thread
     5. the Lead replies `approve` in the data-centre thread
     6. the Lead replies `approve` in the HQ electricity thread
     7. `@collector what is Warehouse-2 October electricity?` <!-- ask -->
     8. `@reporter draft` <!-- report.draft -->
     9. `@carbon-room publish` <!-- close.publish --> (Lead only)
     10. `@reporter trace S-001` <!-- report.trace -->
     11. `@reporter verify audit` <!-- audit.verify -->
   - Also show `@carbon-room status` <!-- close.status --> and `@carbon-room resume` <!-- close.resume -->.
   - Add one line on the fallback, for example `G-2 pick A` <!-- gap.fallback -->, noting that the number comes
     from the thread's title.
5. **Traps and the rules that catch them.** A table of the four traps from contracts §10, with the rule, the
   thread owner and the reply that fixes each, plus the data-centre line (R6, informational).
6. **What is synthetic and what is not claimed.**
   - The seed data is synthetic and labelled on every page.
   - The figures are illustrative.
   - Wispr is not integrated.
   - This is not legal or assurance advice.
   - Scope 3 categories are listed as no data, not zero.
7. **Spike results and fallbacks.** Copy the S1–S6 summary table from `docs/spikes.md`, and say plainly which
   fallback each `CARBON_ROOM_*` setting selects.
8. **Architecture.** Link `Carbon Room Architecture.html`, and give a five-line description of the data flow from
   plan §3.1.
9. **Team and track.** P1 (Ujjwal), P2 (Richa), P3 (Akshar). Track 01, Best Business Workflow.
10. **Numbers.** Totals, coverage and tCO2e come from `data/seed/EXPECTED.md` only. If it is missing, write
    `see data/seed/EXPECTED.md` and give no number. The fake-core figures must never appear.
11. **Commands.** Every `make <target>` mentioned exists in the `Makefile`.

## 6. Test plan

**`tests/test_publish_needs_room.py`**

| Test | Act | Assert |
|---|---|---|
| `test_cli_has_no_publish_resolve_or_approve` | `subprocess.run([sys.executable, "-m", "carbon_room", "--help"], capture_output=True, text=True)` | exit 0; none of `publish`, `resolve` or `approve` is in `stdout.lower()` |
| `test_ingest_file_needs_room_message` | `core.ingest_file("2026-10-v1", "x.pdf", Actor("human", "lead", "Lead", "lead"), "")` | raises `NeedsRoomEvent` |
| `test_publish_needs_room_message` | `core.publish("2026-10-v1", Actor("human", "lead", "Lead", "lead"), "")` | raises `NeedsRoomEvent`. If it raises `NotImplementedError`, call `pytest.skip("P2 publish not merged")` |
| `test_only_room_code_calls_resolve_or_publish` | scan every `carbon_room/**/*.py` except those under `carbon_room/room/` and `carbon_room/agents/`, and except `carbon_room/core.py` | no match for `\bcore\.(resolve\|publish)\(` |

Run the ingest and publish tests with `monkeypatch.chdir(tmp_path)`, so no real `var/` is touched.

**`tests/room/test_readme.py`**

| Test | Act | Assert |
|---|---|---|
| `test_readme_headings_in_order` | collect the lines of `README.md` starting with `## ` | they equal the nine headings in §4, in order (other `##` headings are not allowed; use `###` for subsections) |
| `test_readme_make_targets_exist` | `re.findall(r"make ([a-z-]+)", readme)` | each is a target in the `Makefile` (parse it as in SPEC-16) |
| `test_readme_demo_commands_parse` | in the "Running the demo close" section, find every `` `(@[^`]+\|G-\d+ [^`]+)` `` followed on the same line by `<!-- (kind) -->` | `grammar.parse(cmd, in_thread=False, today=date(2026, 11, 5)).kind == kind` for each; at least 8 commands checked |
| `test_readme_has_no_fake_totals` | — | none of `22.9`, `29.2`, `13.2`, `29184` or `22900` is in `README.md` |
| `test_readme_cites_needs_room_test` | — | `tests/test_publish_needs_room.py` is in the README, and that file exists |
| `test_readme_links_exist` | the relative Markdown links `](path)` that are not `http` | each path exists in the repo |

## 7. Fixtures and doubles
None. The `test_publish_needs_room` tests call the real `carbon_room.core`.

## 8. Manual check
M6: someone who didn't write it follows the README on a clean machine to "Published v1". Log the snags in
`docs/clean-machine-run.md`, then fix the README in small PRs.

## 9. Done when
- [ ] A teammate who didn't write it follows it to a published close without asking a question (checked in M6)
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `tests/room tests/test_publish_needs_room.py`

## 10. Not in this spec
The demo script (M4), the video (M7) and `docs/architecture.png` (the HTML link is enough).

## 11. Open questions
1. Plan §1.4 Q6: P3 writes `tests/test_publish_needs_room.py` (this spec). Tell P1 and P2 in the team chat.
2. If `EXPECTED.md` still doesn't exist at execution time, the README carries no numbers (rule 10). Add them in a
   follow-up PR when it lands.
