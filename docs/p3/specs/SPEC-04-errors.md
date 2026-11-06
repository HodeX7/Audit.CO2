# SPEC-04 · Errors people can act on
Stories: P3-3.5 · Branch: `p3-s04-errors` · PR title: "P3-S04 (3.5): errors people can act on"
Depends on (must be merged): SPEC-01 · Wave: 1 · Estimated session time: 0.5 h

## 1. Goal
Map any exception that reaches the room to a short reply that tells the person what to do next. The reply never
shows a traceback or a secret. Unexpected errors get an 8-character error id that also appears in the log, so a
person can quote it.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2 and §3.8
- `00-CONTRACTS.md` §2 (the exception classes at the end)
- `carbon_room/models.py` (exception classes)

## 3. Files
- Create `carbon_room/room/errors.py`
- Create `tests/room/test_errors.py`

## 4. Public interface
```python
@dataclass(frozen=True)
class ErrorReply:
    text: str
    error_id: str | None

def reply_for(exc: BaseException, *, agent: str | None = None,
              owner_name: str | None = None) -> ErrorReply
```

## 5. Behaviour
1. **Order of checks.** The `isinstance` checks run in the order of the table in rule 3, so subclasses match
   before `CarbonRoomError` and `ValueError`.
2. **`detail`** is `str(exc).strip()`, cut to its first line, with trailing `.` characters removed. When the
   detail is empty, the `: {detail}` or ` ({detail})` part is omitted, as each row shows.
3. **Reply text by exception:**

| Exception | `text` | `error_id` |
|---|---|---|
| `NeedsRoomEvent` | the generic text (last row) | new id |
| `NotAllowed` with `owner_name` | `Only the Lead or the gap owner ({owner_name}) can do that.` | None |
| `NotAllowed` without `owner_name` | `Only the Lead can do that.` | None |
| `LockHeld` | `@collector is still reading that source. Try again in a moment.` | None |
| `BudgetExceeded` | `@{agent or "carbon-room"} has hit its budget for this close and has stopped. The Lead can raise it in config.` | None |
| `NotFound` | `I can't find that: {detail}.`; with no detail, `I can't find that.` | None |
| `NotImplementedError` | `That step isn't built yet ({detail}). The ledger is unchanged.`; with no detail, `That step isn't built yet. The ledger is unchanged.` | None |
| `ValueError` (and subclasses) | `I couldn't do that: {detail}.`; with no detail, `I couldn't do that.` | None |
| anything else (including a bare `CarbonRoomError`) | `Something went wrong on my side (error {error_id}). The ledger is unchanged.` | new id |

4. **Error ids.** A new id is `secrets.token_hex(4)`: 8 lowercase hex characters.
5. **Logging**, on `logging.getLogger("carbon_room.room.errors")`:
   - For the generic row, log at ERROR: `f"unhandled error {error_id}: {type(exc).__name__}"`, with
     `exc_info=exc`.
   - For `NeedsRoomEvent`, log at ERROR: `f"bug: a human action reached core without a chat message id (error
     {error_id})"`, with `exc_info=exc`.
   - Other rows don't log.
6. **Purity.** `reply_for` never raises, does no I/O except the log calls, and never includes the exception type
   name or a traceback in `text`. Only the rows with `{detail}` include exception text.

## 6. Test plan
Build exceptions directly from `carbon_room.models`.

| Test | Act | Assert |
|---|---|---|
| `test_not_allowed_with_owner` | `reply_for(NotAllowed("x"), owner_name="@priya")` | `== ErrorReply("Only the Lead or the gap owner (@priya) can do that.", None)` [3] |
| `test_not_allowed_without_owner` | `reply_for(NotAllowed("x"))` | text `"Only the Lead can do that."` [3] |
| `test_lock_held` | `reply_for(LockHeld("busy"))` | text `"@collector is still reading that source. Try again in a moment."` [3] |
| `test_budget_exceeded_default_agent` | `reply_for(BudgetExceeded("x"))` | text `"@carbon-room has hit its budget for this close and has stopped. The Lead can raise it in config."` [3] |
| `test_budget_exceeded_named_agent` | `reply_for(BudgetExceeded("x"), agent="collector")` | text starts with `"@collector has hit its budget"` [3] |
| `test_not_found` | `reply_for(NotFound("unknown tag: S-099"))`; `reply_for(NotFound())` | `"I can't find that: unknown tag: S-099."`; `"I can't find that."` [2, 3] |
| `test_not_implemented` | `reply_for(NotImplementedError("owner: P2, story P2-2.1"))`; `reply_for(NotImplementedError())` | `"That step isn't built yet (owner: P2, story P2-2.1). The ledger is unchanged."`; `"That step isn't built yet. The ledger is unchanged."` [3] |
| `test_value_error` | `reply_for(ValueError("gap G-2 is already resolved"))` | `"I couldn't do that: gap G-2 is already resolved."` [3] |
| `test_value_error_detail_trimmed` | `reply_for(ValueError("  bad month.\nsecond line"))` | `"I couldn't do that: bad month."` [2] |
| `test_value_error_subclass` | `reply_for(UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"))` | text starts with `"I couldn't do that: "` [1] |
| `test_generic_error_id_is_8_hex_and_logged` | `caplog.set_level(logging.ERROR)`; `reply_for(RuntimeError("boom"))` | `re.fullmatch(r"[0-9a-f]{8}", r.error_id)`; `r.text == f"Something went wrong on my side (error {r.error_id}). The ledger is unchanged."`; one ERROR record contains `r.error_id` and has `exc_info` [3–5] |
| `test_bare_carbon_room_error_is_generic` | `reply_for(CarbonRoomError("x"))` | `error_id` is not None [3] |
| `test_ids_differ` | two generic calls | different ids [4] |
| `test_needs_room_event_logged_as_bug` | caplog; `reply_for(NeedsRoomEvent("x"))` | the text is the generic text with its id; an ERROR record contains `"bug: a human action reached core without a chat message id"` [3, 5] |
| `test_known_errors_do_not_log` | caplog at DEBUG; `reply_for(NotAllowed("x"))`, `reply_for(ValueError("y"))` | no records from `carbon_room.room.errors` [5] |
| `test_error_text_never_contains_traceback_or_key` | `reply_for(RuntimeError("Bearer sk-secret-123"))`; `reply_for(KeyError("sk-secret-123"))` | neither text contains `sk-secret`, `Traceback`, `RuntimeError` or `KeyError` [6] |
| `test_every_contract_exception_has_a_message` (parametrized over `CarbonRoomError, NeedsRoomEvent, NotAllowed, LockHeld, BudgetExceeded, NotFound`) | `reply_for(cls("x"))` | the text is non-empty and ends with `.` [Done when] |

## 7. Fixtures and doubles
None.

## 8. Manual check
None.

## 9. Done when
- [ ] Every exception type in contracts §2 has a tested message
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`

## 10. Not in this spec
Posting the reply. That is `app.on_error` (SPEC-15) and the handlers (SPEC-13).

## 11. Open questions
None.
