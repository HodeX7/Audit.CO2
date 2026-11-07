# SPEC-16 · Makefile, `make doctor`, `make reset-demo` (local part)
Stories: P3-6.1, P3-6.2, P3-6.3 (local part) · Branch: `p3-s16-make-doctor` · PR title: "P3-S16 (6.1, 6.2, 6.3): Makefile, doctor and local reset"
Depends on (must be merged): SPEC-03, SPEC-06 · Wave: 2 · Estimated session time: 1.5 h

> **Split (proposed by the spec writer; noted in plan §5 S16).** The plan's S16 also covered archiving and
> recreating the room. That part needs SPEC-08 and M2's op argument names, and it would block the Friday 12:00
> README deadline. It moves to **SPEC-16B**. Here, `reset` without `--local-only` does the local reset and then
> prints the manual room steps. SPEC-16B replaces that.

## 1. Goal
Make reproduction a few typed commands:
- A **Makefile** whose targets each say what they do.
- **`make doctor`**, which checks every precondition in order and prints a tick, or a cross with the exact fix.
- **`make reset-demo`**, which wipes the local ledger, outputs and inbox after a typed confirmation, then
  re-initialises the database.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §1.3, §2 and §3.10
- `00-CONTRACTS.md` §9 (`llm.mode`)
- `carbon_room/__main__.py` (the `init` command)
- `carbon_room/sources/cache.py`, for the cache path only (`data/cache/extractions/<sha256>.json`). Don't import it.
- `carbon_room/room/settings.py` (`read_env`, `missing`) and `carbon_room/room/identity.py` (`placeholders`)

## 3. Files
- Create `Makefile`, `carbon_room/room/doctor.py`, `carbon_room/room/reset.py` and `scripts/reset_demo.sh`
  (executable: `chmod +x`, and commit it with mode 100755)
- Create `tests/room/test_doctor.py`, `tests/room/test_reset.py` and `tests/room/test_makefile.py`

## 4. Public interface
```python
# doctor.py
@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str

CHECK_NAMES: tuple[str, ...] = (
    "Docker is running", "Switch server answers /health", "Four agent keys are in .env", "Room id is set",
    "people.yaml has no placeholders", "carbon_room.yaml is present", "Database initialises",
    "Replay cache covers every seed file", "API key present (live mode only)")
def run_checks(*, env: Mapping[str, str], runner: Callable[..., Any] = subprocess.run,
               transport: httpx.BaseTransport | None = None, repo_root: Path = Path(".")) -> list[Check]
def format_checks(checks: list[Check]) -> str
def main() -> int

# reset.py
PROMPT: str = "This deletes var/, out/ and data/inbox/ and archives the room. Type reset to continue: "
ROOM_STEPS: str = ("Room reset isn't automated yet. In Mattermost, archive october-close and create a new "
                   "october-close, invite the four agents, and put its id in .env as SWITCH_ROOM_ID.")
def reset_local(repo_root: Path) -> list[Path]
def main(argv: Sequence[str] | None = None, *, input_fn: Callable[[str], str] = input,
         runner: Callable[..., Any] = subprocess.run, repo_root: Path = Path(".")) -> int
```

## 5. Behaviour

### Makefile (exact content in §7)
1. `PY ?= .venv/bin/python`. Every target's first recipe line is `@echo "→ <what it does>"`. The targets are
   `help setup seed register doctor run reset-demo test lint refresh-cache`, all `.PHONY`, with `help` as the
   default (first) target.

### Doctor
2. **`run_checks`** returns exactly 9 `Check`s, named and ordered as in `CHECK_NAMES`. A failing check never
   stops the later ones. Each check:
   1. **Docker is running.** `runner(["docker", "info"], capture_output=True, timeout=20)`.
      - Exit 0 is ok, with detail `""`.
      - `FileNotFoundError` gives detail `docker is not installed`.
      - A non-zero exit gives detail `docker info failed`.
      - `subprocess.TimeoutExpired` gives detail `docker info timed out`.
      - The fix is always `Start Docker Desktop (the bundled Mattermost needs it).`
   2. **Switch server answers /health.** `server = env.get("SWITCH_SERVER", "").strip().rstrip("/")`.
      - **Empty:** detail `SWITCH_SERVER is not set`, fix `Put the server address from Switch Console in .env as
        SWITCH_SERVER.`
      - **Otherwise:** `httpx.Client(transport=transport, timeout=5).get(f"{server}/health")`.
        - A response whose `content-type` contains `text/html`, or whose stripped text starts with `<`: detail
          `that address served a web page`, fix `That's the Gateway. Use the server address Switch Console shows,
          not the Gateway.`
        - Otherwise 200 is ok, with the detail set to the server.
        - 401: detail `401 from /health`, fix `Right host, wrong path: use the server address, not the Gateway.`
        - Other statuses: detail `/health returned <status>`, fix `Check the server address in Switch Console.`
        - `httpx.TransportError`: detail `can't reach <server>`, fix `Start the server in Switch Console (Run a
          server on this computer), then copy its address.`
   3. **Four agent keys are in .env.** `names = [n for n in settings.missing(env) if
      n.startswith("SWITCH_AGENT_")]`. It is ok when `names` is empty. Otherwise the detail is `missing: ` plus
      the names joined with `, `. The fix is `Run make register.`
   4. **Room id is set.** `SWITCH_ROOM_ID` is non-empty after `strip()`. Fix: `Create the october-close room and
      put its id in .env as SWITCH_ROOM_ID (docs/setup-switch.md).`
   5. **people.yaml has no placeholders.** `problems = identity.placeholders()`. It is ok when empty. Otherwise
      the detail is `"; ".join(problems)`. Fix: `Fill in switch_ids and username for lead and priya in
      config/people.yaml (docs/setup-switch.md).`
   6. **carbon_room.yaml is present.**
      `config_dir = Path(env.get("CARBON_ROOM_CONFIG_DIR") or repo_root / "config")`. It is ok when
      `(config_dir / "carbon_room.yaml").is_file()`. Fix: `Pull main; P2 owns config/carbon_room.yaml.`
   7. **Database initialises.** `runner([sys.executable, "-m", "carbon_room", "init"], cwd=repo_root,
      capture_output=True, text=True, timeout=60)`.
      - Exit 0 is ok.
      - Otherwise the detail is the last non-empty line of stderr, or `exit <code>`.
      - Fix: `Run .venv/bin/python -m carbon_room init and read the error.`
      - It never imports `carbon_room.ledger`.
   8. **Replay cache covers every seed file.** `mode` is `llm.mode` from `config_dir / "carbon_room.yaml"`, read
      with `yaml.safe_load`.
      - When the file is missing: ok, detail `skipped: no carbon_room.yaml`.
      - When `mode != "replay"`: ok, detail `not needed (mode=<mode>)`.
      - Otherwise, every regular file in each `repo_root/data/seed/*/` directory (one level, non-recursive) whose
        suffix isn't `.json` needs `repo_root/data/cache/extractions/<sha256 of its bytes>.json`.
      - Missing entries give detail `<n> seed file(s) have no cached extraction: <names, sorted, comma-joined>`.
        Fix: `Run make refresh-cache with an API key, or set llm.mode to rules in config/carbon_room.yaml (ask P2).`
   9. **API key present (live mode only).**
      - When `mode == "live"`: ok if `ANTHROPIC_API_KEY` is non-empty. Fix: `Put ANTHROPIC_API_KEY in .env, or
        use llm.mode rules or replay.`
      - Otherwise: ok, detail `not needed (mode=<mode>)`, where `<mode>` is `unknown` when the yaml is missing.
3. **`format_checks(checks)`.**
   - Each ok check is one line, `✓ <name>`.
   - Each failed check is `✗ <name> — <detail>`, then a line `    fix: <fix>` (four spaces).
   - The last line is `All 9 checks passed.` or `<n> of 9 checks failed.`
   - Lines are joined with `\n`.
4. **`main()`.** `env = settings.read_env(".env")`, then `print(format_checks(run_checks(env=env)))`. It returns 1
   if any check failed, else 0. It never prints a key's value; only variable names appear.

### Reset (local part)
5. **Arguments.** `--yes` and `--local-only`.
6. **Confirmation.** Unless `--yes`, `answer = input_fn(PROMPT)`. Unless `answer.strip() == "reset"`, print
   `Cancelled.`, delete nothing and return 1.
7. **`reset_local(repo_root)`.**
   - **`var/` and `out/`.** Each one is removed when present: a symlink is `unlink`ed and never followed, and a
     directory is `shutil.rmtree`d.
   - **`data/inbox/`.** Every child except `.gitkeep` is removed: files and symlinks are unlinked, and
     directories are `rmtree`d. The directory and its `.gitkeep` stay. A missing `data/inbox/` is created with an
     empty `.gitkeep`.
   - **Containment.** Every path removed must satisfy
     `path.parent.resolve() == (repo_root / <its parent>).resolve()`, and lie under `repo_root.resolve()`. Paths
     are built from `repo_root` only, never from input.
   - **Never touched:** `data/seed`, `data/demo_uploads`, `config/`, `.env` and anything outside `repo_root`.
   - It returns the removed paths, in removal order.
8. **Re-initialise.** `runner([sys.executable, "-m", "carbon_room", "init"], cwd=repo_root, capture_output=True,
   text=True)`. A non-zero exit prints `Database init failed: <last stderr line>` and returns 1.
9. **Room.** Unless `--local-only`, print `ROOM_STEPS`. SPEC-16B replaces this branch.
10. **Done.** Print `Reset done.` and return 0.

### `scripts/reset_demo.sh` (exact)
```bash
#!/usr/bin/env bash
# Reset the demo: wipe var/, out/ and data/inbox/, re-initialise the ledger (asks first). Used by make reset-demo.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
exec "$PY" -m carbon_room.room.reset "$@"
```

## 6. Test plan
**Doctor tests** build a passing baseline:
- `env` holds `SWITCH_SERVER="http://sw.test"`, `SWITCH_ROOM_ID="room-1"` and all 8 agent variables, with
  `CARBON_ROOM_CONFIG_DIR` set to the `people_config` dir.
- `runner` is a fake returning `SimpleNamespace(returncode=0, stdout="", stderr="")` and recording its argv.
- The transport is `MockTransport` answering 200 `{"status": "ok"}` with `content-type: application/json`.
- `repo_root=tmp_path` holds `data/seed/2026-10/a.pdf` (bytes `b"A"`), `data/seed/2026-10/b.json`, and
  `config_dir/carbon_room.yaml` with `llm: {mode: rules}` (the fixture's file already says `rules`).

Each failure test breaks exactly one thing and asserts that check's `ok is False` and its exact `detail` and
`fix`.

| Test | Break | Assert |
|---|---|---|
| `test_all_green` | nothing | 9 checks; all ok; `[c.name for c in checks] == list(CHECK_NAMES)`; `format_checks(...)` ends with `"All 9 checks passed."` [2, 3] |
| `test_docker_not_running` | the runner returns `returncode=1` for `docker info` | check 1: detail `"docker info failed"`, fix `"Start Docker Desktop (the bundled Mattermost needs it)."` |
| `test_docker_missing` | the runner raises `FileNotFoundError` for docker | detail `"docker is not installed"` |
| `test_switch_unset` | `SWITCH_SERVER=""` | check 2: detail `"SWITCH_SERVER is not set"`, fix `"Put the server address from Switch Console in .env as SWITCH_SERVER."`; no HTTP request |
| `test_switch_401` | `/health` returns 401 | fix `"Right host, wrong path: use the server address, not the Gateway."` |
| `test_switch_gateway_html` | 200, `content-type: text/html`, body `<html>…` | detail `"that address served a web page"`, fix starts `"That's the Gateway."` |
| `test_switch_unreachable` | the transport raises `httpx.ConnectError` | detail `"can't reach http://sw.test"` |
| `test_switch_other_status` | 503 | detail `"/health returned 503"` |
| `test_agent_keys_missing` | remove the watchdog KEY and the reporter ID | check 3: detail `"missing: SWITCH_AGENT_WATCHDOG_KEY, SWITCH_AGENT_REPORTER_ID"`, fix `"Run make register."` |
| `test_room_id_missing` | `SWITCH_ROOM_ID=" "` | check 4 fails with its fix |
| `test_people_placeholders` | a config dir whose `people.yaml` has an empty `switch_ids` for lead | check 5: detail `"lead: switch_ids is empty"` |
| `test_carbon_room_yaml_missing` | delete it from the config dir | check 6 fails with `"Pull main; P2 owns config/carbon_room.yaml."`; check 8 is ok with `"skipped: no carbon_room.yaml"`; check 9 is ok with `"not needed (mode=unknown)"` |
| `test_db_init_fails` | the runner returns `returncode=1, stderr="boom\nsqlite3.OperationalError: locked\n"` for the init argv | check 7: detail `"sqlite3.OperationalError: locked"`; the argv was `[sys.executable, "-m", "carbon_room", "init"]` with `cwd=tmp_path` |
| `test_replay_cache_missing` | `llm: {mode: replay}` | check 8: detail `"1 seed file(s) have no cached extraction: a.pdf"` |
| `test_replay_cache_present` | `mode: replay`; create `data/cache/extractions/<sha256(b"A")>.json` | check 8 ok |
| `test_live_mode_needs_api_key` | `mode: live`, no `ANTHROPIC_API_KEY` | check 9 fails with its fix; with `ANTHROPIC_API_KEY=x` it is ok |
| `test_format_checks_failure_layout` | `[Check("A", True, "", ""), Check("B", False, "d", "f")]` | `format_checks(...) == "✓ A\n✗ B — d\n    fix: f\n1 of 9 checks failed."` [3] |
| `test_doctor_never_prints_keys` | `env` keys set to `"key-secret"`; monkeypatch `settings.read_env` to return it; run `main()` with `capsys` | `"key-secret"` not in stdout [4] |

**Reset tests** run in `repo = tmp_path` with this layout: `var/carbon_room.db`, `var/store/x.pdf`,
`out/2026-10/v1/coverage.html`, `data/inbox/.gitkeep`, `data/inbox/bill.pdf`, `data/inbox/sub/y.pdf`,
`data/seed/2026-10/a.pdf`, `data/demo_uploads/d.pdf`, `config/sites.yaml` and `.env`. The runner fake returns
`returncode=0`.

| Test | Act | Assert |
|---|---|---|
| `test_reset_cancelled_deletes_nothing` | `main([], input_fn=lambda p: "no", runner=fake, repo_root=repo)` | returns 1; stdout has `"Cancelled."`; every file still exists; the runner wasn't called; the prompt passed was `PROMPT` [6] |
| `test_reset_local_keeps_gitkeep_and_seed` | `main(["--yes", "--local-only"], …)` | returns 0; `var/` and `out/` are gone; `data/inbox/` holds only `.gitkeep`; seed, demo_uploads, config and `.env` are untouched; the init argv ran; stdout ends with `"Reset done."` and has no `ROOM_STEPS` [7, 8, 10] |
| `test_reset_never_leaves_repo_root` | `outside = tmp_path.parent / "keep.txt"`; make `repo/var` a **symlink** to a dir holding `outside`; make `data/inbox/link.pdf` a symlink to `outside` | `reset_local(repo)` | `outside` and the symlink's target dir still exist with their contents; both links were removed [7] |
| `test_reset_typed_confirmation` | `input_fn=lambda p: "  reset "` | proceeds; returns 0 [6] |
| `test_reset_prints_room_steps_without_local_only` | `main(["--yes"], …)` | stdout contains `ROOM_STEPS` [9] |
| `test_reset_init_failure` | the runner returns `returncode=2, stderr="bad\n"` | returns 1; stdout `"Database init failed: bad"` [8] |
| `test_reset_creates_missing_inbox` | remove `data/inbox` | `reset_local(repo)` | `data/inbox/.gitkeep` exists [7] |
| `test_reset_script_is_executable_and_exact` | read `scripts/reset_demo.sh` | — | it starts with `#!/usr/bin/env bash`; `os.access(path, os.X_OK)`; contains `-m carbon_room.room.reset "$@"` |

**Makefile tests**

| Test | Act | Assert |
|---|---|---|
| `test_makefile_targets_exist_and_echo` | parse `Makefile` for lines matching `^([a-z-]+):` | the set is `{"help", "setup", "seed", "register", "doctor", "run", "reset-demo", "test", "lint", "refresh-cache"}`; each target's first recipe line starts with `\t@echo "→ ` [1] |
| `test_make_dry_run_every_target` | skip if `shutil.which("make")` is None | `subprocess.run(["make", "-n", t], capture_output=True)` for each target | return code 0 [1] |
| `test_help_is_default_target` | — | `make -n` with no target | its output contains `Carbon Room make targets` [1] |

## 7. Fixtures and doubles
`people_config` (SPEC-01), `httpx.MockTransport`, and fake `runner` and `input_fn` callables.

**`Makefile` (exact; recipe lines start with a tab):**
```make
PY ?= .venv/bin/python
P3_PATHS := carbon_room/room carbon_room/agents tests/room tests/fakes

.PHONY: help setup seed register doctor run reset-demo test lint refresh-cache

help:
	@echo "→ Carbon Room make targets"
	@echo "  setup          create .venv and install carbon-room with pytest and ruff"
	@echo "  seed           rebuild the synthetic seed documents"
	@echo "  register       register the four Switch agents and write their keys to .env"
	@echo "  doctor         check Docker, Switch, .env, config and the database"
	@echo "  run            start the four room agents"
	@echo "  reset-demo     wipe the ledger, outputs and inbox (asks first)"
	@echo "  test           run the test suite"
	@echo "  lint           ruff on the P3 paths"
	@echo "  refresh-cache  rebuild the replay cache (needs an API key)"

setup:
	@echo "→ Creating .venv if missing and installing carbon-room with pytest and ruff"
	@test -x .venv/bin/python || python3 -m venv .venv
	$(PY) -m pip install -q -e . pytest ruff

seed:
	@echo "→ Rebuilding the synthetic seed documents in data/seed/"
	$(PY) scripts/make_seed.py

register:
	@echo "→ Registering the four Switch agents (keys go to .env, never to the screen)"
	$(PY) -m carbon_room.room.register

doctor:
	@echo "→ Checking Docker, Switch, .env, config and the database"
	$(PY) -m carbon_room.room.doctor

run:
	@echo "→ Starting carbon-room, collector, watchdog and reporter (Ctrl-C to stop)"
	$(PY) -m carbon_room.room.run

reset-demo:
	@echo "→ Resetting the demo (asks before deleting anything)"
	PY=$(PY) scripts/reset_demo.sh

test:
	@echo "→ Running the test suite"
	$(PY) -m pytest -q

lint:
	@echo "→ Running ruff on the P3 paths"
	$(PY) -m ruff check $(P3_PATHS)

refresh-cache:
	@echo "→ refresh-cache needs P1's live-extraction command, which isn't provided yet"
	@exit 1
```
`P3_PATHS` uses directories, because ruff fails on a path that doesn't exist yet. `carbon_room/agents/__init__.py`
(P1's) passes ruff on `main` today. Before committing, check that `$(PY) scripts/make_seed.py` runs with no
arguments. If it needs any, record that under Deviations.

## 8. Manual check
- On a fresh clone: `make setup seed doctor test`. The doctor shows the expected crosses (Switch, keys, room,
  people) with their fixes.
- `make reset-demo`, then type `no`: nothing is deleted. Run it again and type `reset`: `var/` is gone and the
  database is recreated.

## 9. Done when
- [ ] `make setup seed doctor test` works on a fresh clone. `doctor` may exit 1 before M1–M3, but it runs
- [ ] Each doctor check fails helpfully when broken
- [ ] Two rehearsals back to back start from an identical local state (manual, M5; the room part is SPEC-16B)
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on the touched paths
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Archiving and recreating the room (SPEC-16B), and `refresh-cache`'s real command (P1).
- README text (SPEC-17).

## 11. Open questions
None block execution. If P1 ships a live-extraction command, `refresh-cache` gets a one-line follow-up PR.
