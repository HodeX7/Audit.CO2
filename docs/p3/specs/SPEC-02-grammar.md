# SPEC-02 · Grammar parser
Stories: P3-3.1 · Branch: `p3-s02-grammar` · PR title: "P3-S02 (3.1): grammar parser"
Depends on (must be merged): SPEC-01 · Wave: 1 · Estimated session time: 1 h

## 1. Goal
Turn the text of a room message into an `Intent`: what the person asked for, with its arguments and the agent it
was addressed to. The parser is pure: no I/O, no config, and it never raises. It also normalises gap-thread
replies such as "Pick a" and "Approved." into option keys.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2 and §3.6
- `00-CONTRACTS.md` §8
- `carbon_room/room/ports.py` (`AGENT_NAMES`)

## 3. Files
- Create `carbon_room/room/grammar.py`
- Create `tests/room/test_grammar.py`
- Create `docs/proposals/002-room-help-command.md` (exact content in §7)

## 4. Public interface
```python
@dataclass(frozen=True)
class Intent:
    kind: str
    args: dict
    target_agent: str | None

def parse(body: str, *, in_thread: bool, today: date) -> Intent
def normalize_reply(text: str) -> tuple[str, str]      # (key, rest)

REASON_TRY_CLOSE: str = "Try: @carbon-room close October 2026"
REASON_TAG: str = "Which source tag? Copy one from the draft."
def reason_unknown_month(word: str) -> str               # f"I don't know the month '{word}'."
```

Intent kinds and their args:

| kind | args | target_agent |
|---|---|---|
| `close.start` | `{"month": "YYYY-MM"}` | `carbon-room` |
| `close.status`, `close.resume`, `close.publish` | `{}` | `carbon-room` |
| `report.draft`, `audit.verify` | `{}` | `reporter` |
| `report.trace` | `{"tag": "S-NNN"}` | `reporter` |
| `help` | `{"reason": str \| None}` | the mentioned agent |
| `ask` | `{"question": str}` | the mentioned agent |
| `gap.reply` | `{"text": str}` | `watchdog` |
| `gap.fallback` | `{"gap_id": "G-n", "text": str}` | `watchdog` |
| `ignore` | `{}` | None |

## 5. Behaviour

### Leading mention
1. **Finding it.** Strip the body. A mention is recognised only at the very start, as the first token. Its form is
   an optional backtick, then `@`, then a name matching `[A-Za-z0-9][A-Za-z0-9._-]*`, then an optional backtick,
   then an optional `,` or `:`, then whitespace or the end of the body.
2. **Agent mentions.** The mention is an *agent mention* when `name.lower()` is in `AGENT_NAMES`. The rest is the
   remaining text, stripped.
3. **Other mentions.** A mention of anyone else (for example `@priya`) is not an agent mention. The whole stripped
   body is then the text.
4. **Later mentions.** A mention that isn't the first token is plain text.

### Precedence (first match wins)
5. **Fallback.** Let `t` be the rest after an agent mention, or the whole stripped body when there is no agent
   mention. If `t` matches `G-<digits>`, case-insensitive, optionally followed by `:` or `,`, then whitespace
   and non-empty reply text, the result is
   `Intent("gap.fallback", {"gap_id": f"G-{int(digits)}", "text": <reply text, stripped, original case>}, "watchdog")`.
   This applies with or without a thread. A bare `G-2` with no reply text is not a fallback.
6. **Agent mention:**
   1. If the rest is empty, the result is `help` with `reason` None.
   2. If the rest is a command owned by the mentioned agent (rules 8–13), return that command's intent.
   3. If `in_thread` is true and `normalize_reply(rest)[0]` is a reply key (rule 14), the result is
      `Intent("gap.reply", {"text": rest}, "watchdog")`.
   4. Otherwise the result is `Intent("ask", {"question": rest}, <mentioned agent>)`.
7. **No agent mention:**
   - When `in_thread` is true: `Intent("gap.reply", {"text": <stripped body>}, "watchdog")`. This includes an
     empty body, which is the attachment-only reply.
   - Otherwise: `Intent("ignore", {}, None)`.

### Commands
Command words are matched case-insensitively. Before matching, the rest has its whitespace collapsed to single
spaces and any trailing `.`, `!` or `?` removed.

8. **`help`**, exactly, for any agent: `help` with `reason` None.
9. **carbon-room, exactly `status`, `resume` or `publish`:** `close.status`, `close.resume` or `close.publish`.
   Extra words mean it isn't a command (`status please` falls through to rule 6).
10. **carbon-room, `close` followed by args:**
    - No args: `help` with `reason=REASON_TRY_CLOSE`.
    - One arg matching `^\d{4}-\d{2}$`: if its month part is 01–12, `close.start` with that month; otherwise
      `help` with `reason_unknown_month(arg)`.
    - One arg that is a month name (rule 12): `close.start` with the default year (rule 13).
    - Two args, where the first is a month name and the second matches `^\d{4}$`: `close.start` with
      `f"{year}-{mm:02d}"`.
    - If the first arg is neither a month name nor `YYYY-MM`: `help` with `reason_unknown_month(<first arg as
      typed>)`. This is checked before the extra-words rule.
    - Anything else (extra words, a bad year, `YYYY-MM` followed by more): `help` with
      `reason=REASON_TRY_CLOSE`.
11. **reporter commands:**
    - Exactly `draft`: `report.draft`.
    - Exactly `verify audit`: `audit.verify`. `verify` alone is not a command.
    - `trace` with exactly one arg matching `^s-?(\d{1,3})$`, case-insensitive: `report.trace` with
      `tag=f"S-{int(n):03d}"`.
    - `trace` with no args, two or more args, or a non-matching arg: `help` with `reason=REASON_TAG`.
12. **Month names.** The full English names, the three-letter abbreviations, and `sept`, in any case. They map to
    01–12.
13. **Default year.** It is `today.year`, or `today.year - 1` when the month number is greater than `today.month`.
    For example, `close December` on 2026-11-05 gives `2025-12`, and `close November` gives `2026-11`.
14. **Commands are bound to their agent.** The same words addressed to another agent fall through to rule 6.
    For example, `@reporter publish` and `@collector status` are both `ask`.

### Replies
15. **Reply keys.** A normalised key is a reply key when it is `approve`, `reject` or `upload`, or matches
    `pick <one token>`.
16. **`normalize_reply(text)`.** First collapse whitespace to single spaces, strip, remove trailing `.` and `!`
    characters, and strip again. Call the result `s`, and let `low = s.lower()`. Then:
    1. `low` is `pick <x>` or `pick option <x>`, where `<x>` is one token: `(f"pick {x}", "")`.
    2. `low` is `approve` or `approved`: `("approve", "")`.
    3. `low` starts with `reject` or `rejected`, followed by the end, whitespace, `:`, `—` or `-`: the result is
       `("reject", reason)`. The reason is the rest of `s` in its original case, after an optional `:`, `—` or
       `-` and surrounding spaces. `rejection` is not a match.
    4. `low` is `upload` or `upload <name>`: `("upload", name)`, where the name keeps its original case. Plain
       `upload` gives `("upload", "")`.
    5. Otherwise: `(low, "")`.
17. **Safety.** `parse` never raises, for any string, including the empty string, lone `@` or backtick
    characters, and unicode.
18. **Literals.** `grammar.py` contains no literal `\d{4}-\d{2}` month (`2026-10`) and no `S-`, `G-` or `CL-`
    followed by digits, not even in docstrings. `tests/test_no_literals.py` enforces this. Write the patterns
    with `\d`.

## 6. Test plan
All `parse` cases use `today=date(2026, 11, 5)`. Write them as one `@pytest.mark.parametrize` table,
`(body, in_thread, kind, args, target)`, with ids. Every row asserts `parse(body, in_thread=…, today=…) ==
Intent(kind, args, target)`.

**`test_parse_table`** [rule numbers in the last column]

| # | body | in_thread | kind | args | target | rules |
|---|---|---|---|---|---|---|
| 1 | `@carbon-room close October` | F | close.start | `{"month": "2026-10"}` | carbon-room | 10, 13 |
| 2 | `@Carbon-Room   CLOSE   oct 2026` | F | close.start | `{"month": "2026-10"}` | carbon-room | 1, 10 |
| 3 | `@carbon-room close December` | F | close.start | `{"month": "2025-12"}` | carbon-room | 13 |
| 4 | `@carbon-room close November` | F | close.start | `{"month": "2026-11"}` | carbon-room | 13 |
| 5 | `@carbon-room close 2026-09` | F | close.start | `{"month": "2026-09"}` | carbon-room | 10 |
| 6 | `@carbon-room close Sept` | F | close.start | `{"month": "2026-09"}` | carbon-room | 12 |
| 7 | `@carbon-room close january 2027` | F | close.start | `{"month": "2027-01"}` | carbon-room | 10 |
| 8 | `@carbon-room close October.` | F | close.start | `{"month": "2026-10"}` | carbon-room | commands |
| 9 | `@carbon-room close Smarch` | F | help | `{"reason": "I don't know the month 'Smarch'."}` | carbon-room | 10 |
| 10 | `@carbon-room close 2026-13` | F | help | `{"reason": "I don't know the month '2026-13'."}` | carbon-room | 10 |
| 11 | `@carbon-room close October please` | F | help | `{"reason": "Try: @carbon-room close October 2026"}` | carbon-room | 10 |
| 12 | `@carbon-room close October 26` | F | help | `{"reason": "Try: @carbon-room close October 2026"}` | carbon-room | 10 |
| 13 | `@carbon-room close` | F | help | `{"reason": "Try: @carbon-room close October 2026"}` | carbon-room | 10 |
| 14 | `@carbon-room status` | F | close.status | `{}` | carbon-room | 9 |
| 15 | `@carbon-room, status` | F | close.status | `{}` | carbon-room | 1 |
| 16 | `@carbon-room: status` | F | close.status | `{}` | carbon-room | 1 |
| 17 | `` `@carbon-room` status `` | F | close.status | `{}` | carbon-room | 1 |
| 18 | `@carbon-room status?` | F | close.status | `{}` | carbon-room | commands |
| 19 | `@carbon-room status of warehouse` | F | ask | `{"question": "status of warehouse"}` | carbon-room | 9, 6 |
| 20 | `@carbon-room resume` | F | close.resume | `{}` | carbon-room | 9 |
| 21 | `@carbon-room publish` | F | close.publish | `{}` | carbon-room | 9 |
| 22 | `@carbon-room help` | F | help | `{"reason": None}` | carbon-room | 8 |
| 23 | `@carbon-room` | F | help | `{"reason": None}` | carbon-room | 6 |
| 24 | `@watchdog help` | F | help | `{"reason": None}` | watchdog | 8 |
| 25 | `@reporter draft` | F | report.draft | `{}` | reporter | 11 |
| 26 | `@reporter trace S-014` | F | report.trace | `{"tag": "S-014"}` | reporter | 11 |
| 27 | `@reporter trace s-14` | F | report.trace | `{"tag": "S-014"}` | reporter | 11 |
| 28 | `@reporter trace S14` | F | report.trace | `{"tag": "S-014"}` | reporter | 11 |
| 29 | `@reporter trace S-1` | F | report.trace | `{"tag": "S-001"}` | reporter | 11 |
| 30 | `@reporter trace` | F | help | `{"reason": "Which source tag? Copy one from the draft."}` | reporter | 11 |
| 31 | `@reporter trace S-1234` | F | help | `{"reason": "Which source tag? Copy one from the draft."}` | reporter | 11 |
| 32 | `@reporter verify audit` | F | audit.verify | `{}` | reporter | 11 |
| 33 | `@reporter VERIFY   Audit` | F | audit.verify | `{}` | reporter | 11 |
| 34 | `@reporter publish` | F | ask | `{"question": "publish"}` | reporter | 14 |
| 35 | `@collector status` | F | ask | `{"question": "status"}` | collector | 14 |
| 36 | `@collector what is Warehouse-2 October electricity?` | F | ask | `{"question": "what is Warehouse-2 October electricity?"}` | collector | 6 |
| 37 | `@watchdog why is G-2 open?` | F | ask | `{"question": "why is G-2 open?"}` | watchdog | 5, 6 |
| 38 | `G-2 pick A` | F | gap.fallback | `{"gap_id": "G-2", "text": "pick A"}` | watchdog | 5 |
| 39 | `g-2 PICK a` | F | gap.fallback | `{"gap_id": "G-2", "text": "PICK a"}` | watchdog | 5 |
| 40 | `G-02: approve` | F | gap.fallback | `{"gap_id": "G-2", "text": "approve"}` | watchdog | 5 |
| 41 | `@watchdog G-3 approve` | F | gap.fallback | `{"gap_id": "G-3", "text": "approve"}` | watchdog | 5 |
| 42 | `@carbon-room G-4 reject: wrong month` | F | gap.fallback | `{"gap_id": "G-4", "text": "reject: wrong month"}` | watchdog | 5 |
| 43 | `G-2 pick A` | T | gap.fallback | `{"gap_id": "G-2", "text": "pick A"}` | watchdog | 5 |
| 44 | `G-2` | F | ignore | `{}` | None | 5, 7 |
| 45 | `G-2` | T | gap.reply | `{"text": "G-2"}` | watchdog | 7 |
| 46 | `pick a` | T | gap.reply | `{"text": "pick a"}` | watchdog | 7 |
| 47 | `Approved.` | T | gap.reply | `{"text": "Approved."}` | watchdog | 7 |
| 48 | `` (empty) | T | gap.reply | `{"text": ""}` | watchdog | 7 |
| 49 | `` (empty) | F | ignore | `{}` | None | 7 |
| 50 | `@watchdog approve` | T | gap.reply | `{"text": "approve"}` | watchdog | 6 |
| 51 | `@watchdog pick B` | T | gap.reply | `{"text": "pick B"}` | watchdog | 6 |
| 52 | `@watchdog approve` | F | ask | `{"question": "approve"}` | watchdog | 6 |
| 53 | `@watchdog what does this mean?` | T | ask | `{"question": "what does this mean?"}` | watchdog | 6 |
| 54 | `@carbon-room status` | T | close.status | `{}` | carbon-room | 6 |
| 55 | `hello everyone` | F | ignore | `{}` | None | 7 |
| 56 | `hello everyone` | T | gap.reply | `{"text": "hello everyone"}` | watchdog | 7 |
| 57 | `@someone-else status` | F | ignore | `{}` | None | 3, 7 |
| 58 | `@priya G-2 pick A` | F | ignore | `{}` | None | 3, 5 |
| 59 | `thanks @watchdog` | F | ignore | `{}` | None | 4 |
| 60 | `@carbon-room @reporter draft` | F | ask | `{"question": "@reporter draft"}` | carbon-room | 1, 6 |

**Other tests**

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_normalize_reply_table` (parametrized) | the rows below | `normalize_reply(text)` | equals the expected tuple [16] |
| `test_parse_never_raises` (parametrized) | `"@"`, `"@@@"`, `"`"`, `"``"`, `"G-"`, `"@carbon-room close 9999-99 x"`, `"@reporter trace S-"`, `"​@carbon-room status"`, `"⚡️"`, `"@carbon-room close " + "x" * 5000` | `parse(b, in_thread=t, today=…)` for t in (True, False) | returns an `Intent` [17] |
| `test_reason_strings_have_no_contract_literals` | — | — | `REASON_TRY_CLOSE`, `REASON_TAG` and `reason_unknown_month("x")` don't match `\d{4}-\d{2}` or `\b(?:CL\|G\|S)-\d+` [18] |
| `test_every_contract_row_has_a_case` | the `test_parse_table` rows | collect kinds | `{"close.start", "close.status", "close.resume", "close.publish", "report.draft", "report.trace", "audit.verify", "ask", "gap.reply", "gap.fallback", "help", "ignore"}` are all present [Done when] |

`test_normalize_reply_table` rows:

| text | expected |
|---|---|
| `Pick a` | `("pick a", "")` |
| `pick A!` | `("pick a", "")` |
| `pick option b` | `("pick b", "")` |
| `  PICK    A  ` | `("pick a", "")` |
| `Approved.` | `("approve", "")` |
| `approve` | `("approve", "")` |
| `Reject: wrong period` | `("reject", "wrong period")` |
| `rejected — duplicate` | `("reject", "duplicate")` |
| `reject - Wrong Site.` | `("reject", "Wrong Site")` |
| `reject` | `("reject", "")` |
| `rejection letter` | `("rejection letter", "")` |
| `upload Bill_Oct.pdf` | `("upload", "Bill_Oct.pdf")` |
| `UPLOAD` | `("upload", "")` |
| `hello` | `("hello", "")` |
| `` (empty) | `("", "")` |

## 7. Fixtures and doubles
No fakes are needed.

**`docs/proposals/002-room-help-command.md` (exact):**
```markdown
# 002 · Room help command and fallback mention

## Problem
Contracts §8 has no way for a person to ask the room what it understands. A bare `@carbon-room`, or a known
command with bad arguments (`@carbon-room close Smarch`), currently has no defined intent.

## Change
Add these rows to the table in `00-CONTRACTS.md` §8:

| Who | Text | Intent | Calls |
|---|---|---|---|
| any human | `@<agent> help`, or a bare `@<agent>` | help | none |
| any human | a known command with bad arguments | help (with a reason) | none |

Add this sentence under the table: "`G-2 pick A` may follow an agent mention, as in `@watchdog G-2 pick A`.
Commands are bound to their agent: `@reporter publish` is a question (`ask`), not a publish."

## Who is affected
P3-3.1 (grammar), P3-6.4 (README command list). P1 and P2 are not affected; no core call changes.

## Decision
Approved by P3, the owner of §8.
```

## 8. Manual check
None. The real-room check is in SPEC-15.

## 9. Done when
- [ ] Every row of contracts §8 has at least one passing case (`test_every_contract_row_has_a_case`)
- [ ] An unknown command gives `ask` (rows 34, 35)
- [ ] "pick a" means `pick A`, and "approved" counts as `approve` (normalize rows)
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
- Deciding which socket accepts an intent (`app.classify`, SPEC-15).
- Matching a reply to a gap's options (SPEC-11).
- Editing `00-CONTRACTS.md`. P3 applies the proposal in its own small PR after this merges.

## 11. Open questions
None block execution. Only a leading mention makes a message a command (rule 1), so "thanks @watchdog" is
chatter. This is deliberate; Switch still delivers such a message as addressed, but the room ignores it.
