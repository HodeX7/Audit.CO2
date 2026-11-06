"""SPEC-02: grammar parser tests."""
# ruff: noqa: E501

from __future__ import annotations

import re
from datetime import date

import pytest

from carbon_room.room.grammar import (
    REASON_TAG,
    REASON_TRY_CLOSE,
    Intent,
    normalize_reply,
    parse,
    reason_unknown_month,
)

TODAY = date(2026, 11, 5)
T, F = True, False
TRY = "Try: @carbon-room close October 2026"
TAG = "Which source tag? Copy one from the draft."

PARSE_ROWS = [
    ("close-october", "@carbon-room close October", F, "close.start", {"month": "2026-10"}, "carbon-room"),
    ("close-oct-2026-caps", "@Carbon-Room   CLOSE   oct 2026", F, "close.start", {"month": "2026-10"}, "carbon-room"),
    ("close-december-prev-year", "@carbon-room close December", F, "close.start", {"month": "2025-12"}, "carbon-room"),
    ("close-november", "@carbon-room close November", F, "close.start", {"month": "2026-11"}, "carbon-room"),
    ("close-iso", "@carbon-room close 2026-09", F, "close.start", {"month": "2026-09"}, "carbon-room"),
    ("close-sept", "@carbon-room close Sept", F, "close.start", {"month": "2026-09"}, "carbon-room"),
    ("close-jan-2027", "@carbon-room close january 2027", F, "close.start", {"month": "2027-01"}, "carbon-room"),
    ("close-trailing-dot", "@carbon-room close October.", F, "close.start", {"month": "2026-10"}, "carbon-room"),
    ("close-smarch", "@carbon-room close Smarch", F, "help", {"reason": "I don't know the month 'Smarch'."}, "carbon-room"),
    ("close-bad-iso-month", "@carbon-room close 2026-13", F, "help", {"reason": "I don't know the month '2026-13'."}, "carbon-room"),
    ("close-please", "@carbon-room close October please", F, "help", {"reason": TRY}, "carbon-room"),
    ("close-bad-year", "@carbon-room close October 26", F, "help", {"reason": TRY}, "carbon-room"),
    ("close-bare", "@carbon-room close", F, "help", {"reason": TRY}, "carbon-room"),
    ("status", "@carbon-room status", F, "close.status", {}, "carbon-room"),
    ("status-comma", "@carbon-room, status", F, "close.status", {}, "carbon-room"),
    ("status-colon", "@carbon-room: status", F, "close.status", {}, "carbon-room"),
    ("status-backticks", "`@carbon-room` status", F, "close.status", {}, "carbon-room"),
    ("status-question", "@carbon-room status?", F, "close.status", {}, "carbon-room"),
    ("status-of-warehouse", "@carbon-room status of warehouse", F, "ask", {"question": "status of warehouse"}, "carbon-room"),
    ("resume", "@carbon-room resume", F, "close.resume", {}, "carbon-room"),
    ("publish", "@carbon-room publish", F, "close.publish", {}, "carbon-room"),
    ("help", "@carbon-room help", F, "help", {"reason": None}, "carbon-room"),
    ("bare-mention", "@carbon-room", F, "help", {"reason": None}, "carbon-room"),
    ("watchdog-help", "@watchdog help", F, "help", {"reason": None}, "watchdog"),
    ("reporter-draft", "@reporter draft", F, "report.draft", {}, "reporter"),
    ("trace-s-014", "@reporter trace S-014", F, "report.trace", {"tag": "S-014"}, "reporter"),
    ("trace-s-14", "@reporter trace s-14", F, "report.trace", {"tag": "S-014"}, "reporter"),
    ("trace-s14", "@reporter trace S14", F, "report.trace", {"tag": "S-014"}, "reporter"),
    ("trace-s-1", "@reporter trace S-1", F, "report.trace", {"tag": "S-001"}, "reporter"),
    ("trace-bare", "@reporter trace", F, "help", {"reason": TAG}, "reporter"),
    ("trace-four-digits", "@reporter trace S-1234", F, "help", {"reason": TAG}, "reporter"),
    ("verify-audit", "@reporter verify audit", F, "audit.verify", {}, "reporter"),
    ("verify-audit-caps", "@reporter VERIFY   Audit", F, "audit.verify", {}, "reporter"),
    ("reporter-publish-is-ask", "@reporter publish", F, "ask", {"question": "publish"}, "reporter"),
    ("collector-status-is-ask", "@collector status", F, "ask", {"question": "status"}, "collector"),
    ("collector-question", "@collector what is Warehouse-2 October electricity?", F, "ask", {"question": "what is Warehouse-2 October electricity?"}, "collector"),
    ("watchdog-why-g2", "@watchdog why is G-2 open?", F, "ask", {"question": "why is G-2 open?"}, "watchdog"),
    ("fallback-plain", "G-2 pick A", F, "gap.fallback", {"gap_id": "G-2", "text": "pick A"}, "watchdog"),
    ("fallback-lower", "g-2 PICK a", F, "gap.fallback", {"gap_id": "G-2", "text": "PICK a"}, "watchdog"),
    ("fallback-leading-zero-colon", "G-02: approve", F, "gap.fallback", {"gap_id": "G-2", "text": "approve"}, "watchdog"),
    ("fallback-after-watchdog", "@watchdog G-3 approve", F, "gap.fallback", {"gap_id": "G-3", "text": "approve"}, "watchdog"),
    ("fallback-after-carbon-room", "@carbon-room G-4 reject: wrong month", F, "gap.fallback", {"gap_id": "G-4", "text": "reject: wrong month"}, "watchdog"),
    ("fallback-in-thread", "G-2 pick A", T, "gap.fallback", {"gap_id": "G-2", "text": "pick A"}, "watchdog"),
    ("bare-gap-no-thread", "G-2", F, "ignore", {}, None),
    ("bare-gap-in-thread", "G-2", T, "gap.reply", {"text": "G-2"}, "watchdog"),
    ("thread-pick", "pick a", T, "gap.reply", {"text": "pick a"}, "watchdog"),
    ("thread-approved", "Approved.", T, "gap.reply", {"text": "Approved."}, "watchdog"),
    ("thread-empty", "", T, "gap.reply", {"text": ""}, "watchdog"),
    ("no-thread-empty", "", F, "ignore", {}, None),
    ("mention-reply-key-in-thread", "@watchdog approve", T, "gap.reply", {"text": "approve"}, "watchdog"),
    ("mention-pick-in-thread", "@watchdog pick B", T, "gap.reply", {"text": "pick B"}, "watchdog"),
    ("mention-reply-key-no-thread", "@watchdog approve", F, "ask", {"question": "approve"}, "watchdog"),
    ("mention-question-in-thread", "@watchdog what does this mean?", T, "ask", {"question": "what does this mean?"}, "watchdog"),
    ("command-in-thread", "@carbon-room status", T, "close.status", {}, "carbon-room"),
    ("chatter", "hello everyone", F, "ignore", {}, None),
    ("chatter-in-thread", "hello everyone", T, "gap.reply", {"text": "hello everyone"}, "watchdog"),
    ("other-mention", "@someone-else status", F, "ignore", {}, None),
    ("other-mention-gap", "@priya G-2 pick A", F, "ignore", {}, None),
    ("later-mention", "thanks @watchdog", F, "ignore", {}, None),
    ("double-mention", "@carbon-room @reporter draft", F, "ask", {"question": "@reporter draft"}, "carbon-room"),
]


@pytest.mark.parametrize(
    "body,in_thread,kind,args,target",
    [r[1:] for r in PARSE_ROWS],
    ids=[r[0] for r in PARSE_ROWS],
)
def test_parse_table(body, in_thread, kind, args, target):
    assert parse(body, in_thread=in_thread, today=TODAY) == Intent(kind, args, target)


NORMALIZE_ROWS = [
    ("Pick a", ("pick a", "")),
    ("pick A!", ("pick a", "")),
    ("pick option b", ("pick b", "")),
    ("  PICK    A  ", ("pick a", "")),
    ("Approved.", ("approve", "")),
    ("approve", ("approve", "")),
    ("Reject: wrong period", ("reject", "wrong period")),
    ("rejected — duplicate", ("reject", "duplicate")),
    ("reject - Wrong Site.", ("reject", "Wrong Site")),
    ("reject", ("reject", "")),
    ("rejection letter", ("rejection letter", "")),
    ("upload Bill_Oct.pdf", ("upload", "Bill_Oct.pdf")),
    ("UPLOAD", ("upload", "")),
    ("hello", ("hello", "")),
    ("", ("", "")),
]


@pytest.mark.parametrize("text,expected", NORMALIZE_ROWS)
def test_normalize_reply_table(text, expected):
    assert normalize_reply(text) == expected


NEVER_RAISES = [
    "@", "@@@", "`", "``", "G-", "@carbon-room close 9999-99 x", "@reporter trace S-",
    "​@carbon-room status", "⚡️", "@carbon-room close " + "x" * 5000,
]


@pytest.mark.parametrize("body", NEVER_RAISES)
@pytest.mark.parametrize("in_thread", [True, False])
def test_parse_never_raises(body, in_thread):
    assert isinstance(parse(body, in_thread=in_thread, today=TODAY), Intent)


def test_reason_strings_have_no_contract_literals():
    for s in (REASON_TRY_CLOSE, REASON_TAG, reason_unknown_month("x")):
        assert not re.search(r"\d{4}-\d{2}", s)
        assert not re.search(r"\b(?:CL|G|S)-\d+", s)


def test_every_contract_row_has_a_case():
    kinds = {r[3] for r in PARSE_ROWS}
    assert kinds >= {
        "close.start", "close.status", "close.resume", "close.publish", "report.draft",
        "report.trace", "audit.verify", "ask", "gap.reply", "gap.fallback", "help", "ignore",
    }
