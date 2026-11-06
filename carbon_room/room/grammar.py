"""Room message text to Intent. Pure: no I/O, no config, never raises."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from carbon_room.room.ports import AGENT_NAMES

REASON_TRY_CLOSE: str = "Try: @carbon-room close October 2026"
REASON_TAG: str = "Which source tag? Copy one from the draft."

_A = re.ASCII
_MENTION = re.compile(r"`?@([A-Za-z0-9][A-Za-z0-9._-]*)`?[,:]?(?:\s+|$)")
_FALLBACK = re.compile(r"G-(\d{1,9})[:,]?\s+(\S.*)", re.IGNORECASE | re.DOTALL | _A)
_ISO_MONTH = re.compile(r"(\d{4})-(\d{2})", _A)
_YEAR = re.compile(r"\d{4}", _A)
_TRACE_TAG = re.compile(r"s-?(\d{1,3})", re.IGNORECASE | _A)
_PICK = re.compile(r"pick(?:\s+option)?\s+(\S+)", re.IGNORECASE)
_REJECT = re.compile(r"reject(?:ed)?(?=$|[\s:\u2014-])", re.IGNORECASE)
_UPLOAD = re.compile(r"upload(?:\s+(.+))?", re.IGNORECASE | re.DOTALL)
_PICK_KEY = re.compile(r"pick \S+")

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTHS: dict[str, int] = {}
for _i, _name in enumerate(_MONTH_NAMES, start=1):
    _MONTHS[_name] = _i
    _MONTHS[_name[:3]] = _i
_MONTHS["sept"] = 9


@dataclass(frozen=True)
class Intent:
    kind: str
    args: dict
    target_agent: str | None


def reason_unknown_month(word: str) -> str:
    return f"I don't know the month '{word}'."


def _ignore() -> Intent:
    return Intent("ignore", {}, None)


def _help(agent: str, reason: str | None = None) -> Intent:
    return Intent("help", {"reason": reason}, agent)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _default_year(month: int, today: date) -> int:
    return today.year - 1 if month > today.month else today.year


def _close(args: list[str], today: date) -> Intent:
    agent = "carbon-room"
    if not args:
        return _help(agent, REASON_TRY_CLOSE)
    first = args[0]
    month = _MONTHS.get(first.lower())
    iso = _ISO_MONTH.fullmatch(first)
    if month is None and iso is None:
        return _help(agent, reason_unknown_month(first))
    if iso is not None:
        if len(args) != 1:
            return _help(agent, REASON_TRY_CLOSE)
        if not 1 <= int(iso.group(2)) <= 12:
            return _help(agent, reason_unknown_month(first))
        return Intent("close.start", {"month": first}, agent)
    if len(args) == 1:
        year = _default_year(month, today)
    elif len(args) == 2 and _YEAR.fullmatch(args[1]):
        year = int(args[1])
    else:
        return _help(agent, REASON_TRY_CLOSE)
    return Intent("close.start", {"month": f"{year}-{month:02d}"}, agent)


def _command(agent: str, rest: str, today: date) -> Intent | None:
    norm = _collapse(rest).rstrip(".!?").strip()
    words = norm.split(" ") if norm else []
    if not words:
        return None
    word = words[0].lower()
    if len(words) == 1 and word == "help":
        return _help(agent)
    if agent == "carbon-room":
        if len(words) == 1 and word in ("status", "resume", "publish"):
            return Intent(f"close.{word}", {}, agent)
        if word == "close":
            return _close(words[1:], today)
    elif agent == "reporter":
        if norm.lower() == "draft":
            return Intent("report.draft", {}, agent)
        if norm.lower() == "verify audit":
            return Intent("audit.verify", {}, agent)
        if word == "trace":
            m = _TRACE_TAG.fullmatch(words[1]) if len(words) == 2 else None
            if m is None:
                return _help(agent, REASON_TAG)
            return Intent("report.trace", {"tag": f"S-{int(m.group(1)):03d}"}, agent)
    return None


def _is_reply_key(key: str) -> bool:
    return key in ("approve", "reject", "upload") or _PICK_KEY.fullmatch(key) is not None


def _parse(body: str, in_thread: bool, today: date) -> Intent:
    text = body.strip()
    agent: str | None = None
    m = _MENTION.match(text)
    if m is not None and m.group(1).lower() in AGENT_NAMES:
        agent = m.group(1).lower()
        text = text[m.end():].strip()

    fb = _FALLBACK.fullmatch(text)
    if fb is not None:
        return Intent(
            "gap.fallback",
            {"gap_id": f"G-{int(fb.group(1))}", "text": fb.group(2).strip()},
            "watchdog",
        )

    if agent is not None:
        if not text:
            return _help(agent)
        cmd = _command(agent, text, today)
        if cmd is not None:
            return cmd
        if in_thread and _is_reply_key(normalize_reply(text)[0]):
            return Intent("gap.reply", {"text": text}, "watchdog")
        return Intent("ask", {"question": text}, agent)

    if in_thread:
        return Intent("gap.reply", {"text": text}, "watchdog")
    return _ignore()


def parse(body: str, *, in_thread: bool, today: date) -> Intent:
    try:
        return _parse(body, in_thread, today)
    except Exception:  # the parser never raises
        return _ignore()


def normalize_reply(text: str) -> tuple[str, str]:
    s = _collapse(text).rstrip(".!").strip()
    low = s.lower()
    m = _PICK.fullmatch(s)
    if m is not None:
        return (f"pick {m.group(1).lower()}", "")
    if low in ("approve", "approved"):
        return ("approve", "")
    m = _REJECT.match(s)
    if m is not None:
        reason = s[m.end():].strip()
        if reason[:1] in (":", "\u2014", "-"):
            reason = reason[1:]
        return ("reject", reason.strip())
    m = _UPLOAD.fullmatch(s)
    if m is not None:
        return ("upload", m.group(1) or "")
    return (low, "")
