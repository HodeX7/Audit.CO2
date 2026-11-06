# SPEC-11 · Router and attachments
Stories: P3-3.3, P3-3.4, P3-2.6 · Branch: `p3-s11-router` · PR title: "P3-S11 (3.3, 3.4, 2.6): router and attachments"
Depends on (must be merged): SPEC-01, SPEC-02, SPEC-06 · Wave: 2 · Estimated session time: 1 h

## 1. Goal
Two pure-ish pieces that SPEC-13's handler composes:
- **The router** matches a person's gap-thread reply ("Pick a", "Approved.", "reject: wrong site", or an
  attachment) to one of the gap's options. It returns the action and its payload, or the reason there is no match.
- **The attachment fetcher** turns an uploaded file into a managed regular file under `data/inbox/`. It works by
  download, or by finding a file the person put there. It never lets a name escape that directory, follow a
  symlink, or pass a file over 10 MiB to P1.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2, §3.6 (`normalize_reply`) and §3.14
- `00-CONTRACTS.md` §6 (options and actions) and §8
- `docs/HANDOFF.md`: P1 rejects symlinked, non-regular and over-10 MiB files, and P3 owns the managed upload
  directory
- `carbon_room/room/grammar.py` and `carbon_room/room/events.py` (`Attachment`)

## 3. Files
- Create `carbon_room/room/router.py`
- Create `carbon_room/room/attachments.py`
- Create `tests/room/test_router.py`
- Create `tests/room/test_attachments.py`

## 4. Public interface
```python
# router.py
@dataclass(frozen=True)
class GapAction:
    gap: Gap
    option: Option
    payload: dict
    filename: str | None

@dataclass(frozen=True)
class NoMatch:
    gap: Gap
    reason: Literal["unknown_reply", "gap_resolved", "no_options"]

def match_reply(gap: Gap, text: str, has_attachment: bool) -> GapAction | NoMatch
def find_gap(gaps: list[Gap], gap_id: str) -> Gap | None

# attachments.py
MAX_BYTES: int = 10 * 1024 * 1024
MAX_NAME: int = 150

class AttachmentMissing(Exception):
    def __init__(self, text: str) -> None
    text: str                       # str(exc) == text

def safe_name(name: str) -> str
async def fetch(*, message_id: str, attachment: Attachment | None, typed_name: str | None, mode: str,
                inbox_dir: Path, download: Callable[[Attachment], Awaitable[bytes]] | None) -> Path
```

## 5. Behaviour

### Router
1. A gap with `status == "RESOLVED"` gives `NoMatch(gap, "gap_resolved")`. Otherwise, a gap with no options gives
   `NoMatch(gap, "no_options")`.
2. **Attachment.** When `has_attachment` is True and the gap has an option with `action == "upload"`, the result
   is `GapAction(gap, that option, dict(option.params), None)`, whatever the text says. When there is no upload
   option, the attachment is ignored and the text is matched.
3. **Text.**
   - `key, rest = normalize_reply(text)`.
   - For each option in order, compare `key` with `normalize_reply(option.key)[0]`. The first equal one matches.
   - `payload = dict(option.params)`, a fresh copy, so the gap's params are never mutated.
   - For `reject` with a non-empty `rest`, add `payload["reason"] = rest`.
   - `filename = rest or None` for `upload`, else None.
4. **No match.** Anything else, including empty text without an attachment, gives `NoMatch(gap,
   "unknown_reply")`.
5. **`find_gap(gaps, gap_id)`** returns the first gap whose `gap_id.lower() == gap_id.lower()`, else None.

### Attachments
6. **`safe_name(name)`:**
   - Replace `\` with `/` and keep the part after the last `/`.
   - Map every character outside `[A-Za-z0-9._-]` to `_`, one `_` per character, unicode included.
   - Raise `AttachmentMissing("That file name isn't usable. Rename it and try again.")` when the result is empty,
     `.` or `..`, or starts with `.`.
   - Raise `AttachmentMissing("That file name is too long. Rename it and try again.")` when it is longer than
     `MAX_NAME`.
7. **Download mode,** used when `mode == "download"`, `attachment` is not None and `download` is not None:
   1. If `attachment.size` is an int > `MAX_BYTES`, raise
      `AttachmentMissing("That file is over 10 MiB, so I can't take it.")` without downloading.
   2. `data = await download(attachment)`. If it raises any `Exception`, log a WARNING and use inbox mode
      instead (rule 8).
   3. If `len(data) > MAX_BYTES`, raise the same over-10-MiB error.
   4. The target is `inbox_dir / f"{safe_name(message_id)}_{safe_name(attachment.filename)}"`.
   5. In a worker thread (`asyncio.to_thread`): `inbox_dir.mkdir(parents=True, exist_ok=True)`, then write with
      `open(target, "xb")`. If the file exists, raise
      `AttachmentMissing(f"I already have a file called {target.name}. Rename it and try again.")`.
   6. Return `target`.
8. **Inbox mode,** used when `mode == "inbox"`, or as the download fallback, or when the attachment or
   `download` is None:
   1. `name = typed_name or (attachment.filename if attachment else None)`. When there is none, raise
      `AttachmentMissing(f"I can't see that file yet. Put it in {inbox_dir.as_posix()}/ and reply upload
      <name>.")`, with the literal text `<name>`.
   2. `safe = safe_name(name)` and `candidate = inbox_dir / safe`.
   3. In a worker thread, check that `candidate` is not a symlink, exists, is a regular file, has a `resolve()`d
      path inside `inbox_dir.resolve()`, and is at most `MAX_BYTES`. The size check fails with the over-10-MiB
      error. Every other failure raises
      `AttachmentMissing(f"I can't see that file yet. Put it in {inbox_dir.as_posix()}/ and reply upload
      {safe}.")`.
   4. Return `candidate`, in the same form as given (relative stays relative).
9. **Unknown mode.** Any other `mode` raises `ValueError(f"unknown attachments mode {mode!r}")`.
10. **Error texts.** Every `AttachmentMissing.text` is a complete sentence the handler posts as is. With the
    default `inbox_dir=Path("data/inbox")`, the missing-file text is the story's exact sentence:
    `I can't see that file yet. Put it in data/inbox/ and reply upload <name>.`

## 6. Test plan
Build gaps with the `FakeCore` scenario: start, ingest, calculate and check, then `resume_state`. `G1`, `G2`, `G3`
and `G4` are those gaps. Async tests use `asyncio.run`. Attachment tests run with `monkeypatch.chdir(tmp_path)`
and `inbox_dir=Path("data/inbox")`, so texts read `data/inbox/`.

**`tests/room/test_router.py`**

| Test | Act | Assert |
|---|---|---|
| `test_pick_a_in_diesel_gap_gives_option_a_params` | `match_reply(G2, "Pick a", False)` | `GapAction(G2, G2.options[0], {"claim_id": "CL-0003"}, None)` [3] |
| `test_pick_b_variants` (parametrized `"pick B"`, `"PICK OPTION b"`, `"pick b!"`) | `match_reply(G2, t, False)` | `.option.key == "pick B"` and `.payload == {"claim_id": "CL-0002"}` [3] |
| `test_hello_gives_unknown_reply` | `match_reply(G2, "hello", False)` | `NoMatch(G2, "unknown_reply")` [4] |
| `test_empty_text_no_attachment` | `match_reply(G2, "", False)` | `NoMatch(G2, "unknown_reply")` [4] |
| `test_approved_counts_as_approve` | `match_reply(G4, "Approved.", False)` | `.option.action == "approve"` and `.payload == {}` [3] |
| `test_reject_reason_in_payload` | `match_reply(G3, "Reject: wrong site", False)`; `match_reply(G3, "reject", False)` | `.payload == {"reason": "wrong site"}`; then `.payload == {}` [3] |
| `test_params_are_copied` | `a = match_reply(G3, "approve", False)`, then `a.payload["x"] = 1` | `G3.options[0].params == {"use_factor_id": "EMBER-2025-IE"}` [3] |
| `test_attachment_counts_as_upload` | `match_reply(G1, "", True)`; `match_reply(G1, "thanks", True)` | both are `GapAction(G1, G1.options[0], {"site": "warehouse-2", "month": "2026-10", "activity": "electricity_kwh"}, None)` [2] |
| `test_attachment_on_gap_without_upload_is_ignored` | `match_reply(G4, "approve", True)`; `match_reply(G4, "", True)` | approve; `NoMatch(G4, "unknown_reply")` [2] |
| `test_upload_typed_name` | `match_reply(G1, "upload Bill_Oct.pdf", False)`; `match_reply(G1, "upload", False)` | `filename == "Bill_Oct.pdf"`; `filename is None` [3] |
| `test_upload_text_on_gap_without_upload` | `match_reply(G2, "upload x.pdf", False)` | `NoMatch(G2, "unknown_reply")` [4] |
| `test_resolved_and_optionless` | `replace(G2, status="RESOLVED")`; `replace(G2, options=[])` | `NoMatch(…, "gap_resolved")`; `NoMatch(…, "no_options")` [1] |
| `test_find_gap_case_insensitive` | `find_gap([G1, G2], "g-2")`, `find_gap([G1, G2], "G-9")` | `G2`; None [5] |

**`tests/room/test_attachments.py`**

`ATT = Attachment("bill.pdf", "application/pdf", 12, "mxc://s/x", "m.file")`

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_safe_name_traversal_and_unicode` (parametrized) | — | `safe_name(x)` | `"../../etc/passwd"` → `"passwd"`; `"bill (1).pdf"` → `"bill__1_.pdf"`; `"C:\\Users\\me\\bill.pdf"` → `"bill.pdf"`; `"rapport_été.pdf"` (NFC) → `"rapport__t_.pdf"`; `"a/b/ok-1.PDF"` → `"ok-1.PDF"` [6] |
| `test_safe_name_rejects` (parametrized `""`, `"."`, `".."`, `".env"`, `"dir/"`, `"x" * 151`) | — | `safe_name(x)` | raises `AttachmentMissing`; the long name's text is `"That file name is too long. Rename it and try again."`, the rest `"That file name isn't usable. Rename it and try again."` [6] |
| `test_download_mode_writes_managed_file` | `download` returns `b"%PDF"` | `fetch(message_id="msg:1", attachment=ATT, typed_name=None, mode="download", inbox_dir=Path("data/inbox"), download=download)` | returns `Path("data/inbox/msg_1_bill.pdf")`; the file holds `b"%PDF"`; the dir was created [7] |
| `test_download_existing_file_refused` | that file already exists | the same fetch | `AttachmentMissing("I already have a file called msg_1_bill.pdf. Rename it and try again.")`; the file is unchanged [7] |
| `test_download_too_big` | `download` returns `b"x" * (MAX_BYTES + 1)`; and a second case with `ATT` `size=MAX_BYTES + 1` and a `download` that fails the test if called | fetch | `AttachmentMissing("That file is over 10 MiB, so I can't take it.")` both times; no file written [7] |
| `test_download_failure_falls_back_to_inbox` | `download` raises `RuntimeError`; `data/inbox/bill.pdf` exists | fetch in download mode | returns `Path("data/inbox/bill.pdf")`; a WARNING was logged [7, 8] |
| `test_download_mode_without_attachment_uses_inbox` | `data/inbox/typed.pdf` exists | `fetch(..., attachment=None, typed_name="typed.pdf", mode="download", download=dl)` | `Path("data/inbox/typed.pdf")`; `dl` not called [8] |
| `test_inbox_mode_finds_file` | `data/inbox/bill.pdf` exists | `fetch(..., attachment=ATT, typed_name=None, mode="inbox", download=None)` | `Path("data/inbox/bill.pdf")` [8] |
| `test_inbox_typed_name_wins` | `data/inbox/other.pdf` exists | `fetch(..., attachment=ATT, typed_name="other.pdf", mode="inbox", …)` | `Path("data/inbox/other.pdf")` [8] |
| `test_inbox_missing_gives_exact_text` | empty inbox | fetch with `typed_name="Bill Oct.pdf"`; and with no attachment and no name | `AttachmentMissing("I can't see that file yet. Put it in data/inbox/ and reply upload Bill_Oct.pdf.")`; `AttachmentMissing("I can't see that file yet. Put it in data/inbox/ and reply upload <name>.")` [8, 10] |
| `test_inbox_rejects_symlink` | `tmp_path/outside.pdf` exists; `data/inbox/link.pdf` is a symlink to it | fetch `typed_name="link.pdf"` | the missing-file text with `link.pdf` [8] |
| `test_inbox_rejects_directory` | `data/inbox/folder.pdf/` is a directory | fetch `typed_name="folder.pdf"` | the missing-file text [8] |
| `test_inbox_rejects_oversize` | `data/inbox/big.pdf` of `MAX_BYTES + 1` bytes (sparse via `truncate`) | fetch `typed_name="big.pdf"` | `AttachmentMissing("That file is over 10 MiB, so I can't take it.")` [8] |
| `test_inbox_traversal_name_stays_inside` | `tmp_path/data/secret.pdf` exists; the inbox is empty | fetch `typed_name="../secret.pdf"` | the missing-file text with `secret.pdf` (not found inside the inbox) [6, 8] |
| `test_unknown_mode` | — | `fetch(..., mode="ftp", …)` | `ValueError("unknown attachments mode 'ftp'")` [9] |

## 7. Fixtures and doubles
`FakeCore` (SPEC-01), for its gap objects only.

## 8. Manual check
None until SPEC-13 and SPEC-15 merge. Then, in the real room, reply `upload warehouse2_electricity_2026-10_actual.pdf`
in the Warehouse-2 thread after copying the demo file into `data/inbox/`.

## 9. Done when
- [ ] "Pick a" in the diesel thread maps to option A's params
- [ ] "hello" maps to `unknown_reply` (SPEC-13 turns that into the options reply)
- [ ] `G-2 pick A` routes with and without a thread. The parse side is SPEC-02; `find_gap` and `match_reply` here
      cover the rest
- [ ] Both attachment paths are tested
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
Calling core, posting replies and role checks (SPEC-13).

## 11. Open questions
None block execution. The real media route is spike S2. Until it passes, `CARBON_ROOM_ATTACHMENTS=inbox` is the
path in use.
