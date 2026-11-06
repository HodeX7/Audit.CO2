"""Errors people can act on (SPEC-04 section 6)."""

from __future__ import annotations

import logging
import re

import pytest

from carbon_room.models import (
    BudgetExceeded,
    CarbonRoomError,
    LockHeld,
    NeedsRoomEvent,
    NotAllowed,
    NotFound,
)
from carbon_room.room.errors import ErrorReply, reply_for

LOGGER = "carbon_room.room.errors"


def test_not_allowed_with_owner():
    assert reply_for(NotAllowed("x"), owner_name="@priya") == ErrorReply(
        "Only the Lead or the gap owner (@priya) can do that.", None
    )


def test_not_allowed_without_owner():
    assert reply_for(NotAllowed("x")).text == "Only the Lead can do that."


def test_lock_held():
    assert reply_for(LockHeld("busy")).text == (
        "@collector is still reading that source. Try again in a moment."
    )


def test_budget_exceeded_default_agent():
    assert reply_for(BudgetExceeded("x")).text == (
        "@carbon-room has hit its budget for this close and has stopped. The Lead can raise it in config."
    )


def test_budget_exceeded_named_agent():
    assert reply_for(BudgetExceeded("x"), agent="collector").text.startswith(
        "@collector has hit its budget"
    )


def test_not_found():
    assert reply_for(NotFound("unknown tag: S-099")).text == "I can't find that: unknown tag: S-099."
    assert reply_for(NotFound()).text == "I can't find that."


def test_not_implemented():
    assert reply_for(NotImplementedError("owner: P2, story P2-2.1")).text == (
        "That step isn't built yet (owner: P2, story P2-2.1). The ledger is unchanged."
    )
    assert reply_for(NotImplementedError()).text == "That step isn't built yet. The ledger is unchanged."


def test_value_error():
    assert reply_for(ValueError("gap G-2 is already resolved")).text == (
        "I couldn't do that: gap G-2 is already resolved."
    )


def test_value_error_detail_trimmed():
    assert reply_for(ValueError("  bad month.\nsecond line")).text == "I couldn't do that: bad month."


def test_value_error_subclass():
    r = reply_for(UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"))
    assert r.text.startswith("I couldn't do that: ")


def test_generic_error_id_is_8_hex_and_logged(caplog):
    caplog.set_level(logging.ERROR)
    r = reply_for(RuntimeError("boom"))
    assert re.fullmatch(r"[0-9a-f]{8}", r.error_id)
    assert r.text == f"Something went wrong on my side (error {r.error_id}). The ledger is unchanged."
    records = [x for x in caplog.records if x.levelno == logging.ERROR]
    assert len(records) == 1
    assert r.error_id in records[0].getMessage()
    assert records[0].exc_info


def test_bare_carbon_room_error_is_generic():
    assert reply_for(CarbonRoomError("x")).error_id is not None


def test_ids_differ():
    assert reply_for(RuntimeError("a")).error_id != reply_for(RuntimeError("a")).error_id


def test_needs_room_event_logged_as_bug(caplog):
    caplog.set_level(logging.ERROR)
    r = reply_for(NeedsRoomEvent("x"))
    assert r.error_id is not None
    assert r.text == f"Something went wrong on my side (error {r.error_id}). The ledger is unchanged."
    assert any(
        "bug: a human action reached core without a chat message id" in x.getMessage()
        for x in caplog.records
        if x.levelno == logging.ERROR
    )


def test_known_errors_do_not_log(caplog):
    caplog.set_level(logging.DEBUG)
    reply_for(NotAllowed("x"))
    reply_for(ValueError("y"))
    assert [x for x in caplog.records if x.name == LOGGER] == []


def test_error_text_never_contains_traceback_or_key():
    for exc in (RuntimeError("Bearer sk-secret-123"), KeyError("sk-secret-123")):
        text = reply_for(exc).text
        for bad in ("sk-secret", "Traceback", "RuntimeError", "KeyError"):
            assert bad not in text


@pytest.mark.parametrize("cls", [CarbonRoomError, NeedsRoomEvent, NotAllowed, LockHeld, BudgetExceeded, NotFound])
def test_every_contract_exception_has_a_message(cls):
    text = reply_for(cls("x")).text
    assert text
    assert text.endswith(".")
