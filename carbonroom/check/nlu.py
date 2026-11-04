"""Translates a loosely-phrased human chat reply (e.g. "yeah go with the
second one") into one of resolve.py's exact recognized resolution strings
("use <id>", a number, "exclude: ...", "accept: ...", "approve"), using an
LLM as a pure intent-translator.

Safety boundary (read this before changing anything here):
  - The model NEVER decides a number, a fact, or which option is correct.
    It only maps the human's own words onto a closed, pre-existing set of
    options that resolve.py already knows how to handle.
  - Every string this returns still goes through resolve_gap()'s own
    validation (e.g. an activity id must actually be in
    candidate_activity_ids) -- this module adds a second, independent
    check on top of that, it does not replace it.
  - If the model can't confidently map the reply, this raises
    NeedsClarificationError instead of guessing. The caller should ask
    the human to rephrase, never silently pick an option.
  - This is the ONLY place in the carbonroom package that calls an LLM.
    Calculator/Checker/Reporter math never does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .. import llm


class NeedsClarificationError(ValueError):
    """Raised when the reply couldn't be confidently translated. The
    caller should ask the human to rephrase using one of the exact
    recognized formats, not retry the model or guess."""


@dataclass(frozen=True)
class CandidateActivity:
    activity_id: str
    description: str  # e.g. "500 gallon, doc-diesel-1"


_RECOGNIZED_FORMATS = (
    '"use <activity_id>" (pick one candidate, excludes the rest)',
    "a bare number like \"1\" or \"2\" (same, by position)",
    '"exclude: <reason>" (drop the one candidate this gap concerns)',
    '"accept: <reason>" (accept the risk, change nothing)',
    '"approve" (send the flagged activity back for re-verification)',
)


def _build_prompt(gap: dict, candidates: list[CandidateActivity], reply_text: str) -> str:
    candidate_lines = "\n".join(f"  {i + 1}. {c.activity_id} -- {c.description}" for i, c in enumerate(candidates))
    formats = "\n".join(f"  - {f}" for f in _RECOGNIZED_FORMATS)
    return f"""You are translating one human's chat reply into EXACTLY ONE line of a fixed
command format. Output ONLY that one line, nothing else -- no explanation, no punctuation
around it, no markdown.

Gap: [{gap['kind']}] {gap.get('detail', '')}

Candidate activities for this gap (if any):
{candidate_lines or "  (none -- this gap has no specific activity to choose between)"}

The human's reply, verbatim, is the ONLY thing to translate -- do not use outside knowledge
or guess what they "probably" meant beyond what they actually wrote:
---
{reply_text}
---

Valid output formats (output must be ONE of these, nothing else):
{formats}

If "use <activity_id>", the id MUST be copied exactly from the candidate list above -- never
invent one. If you cannot confidently tell which of these formats the reply maps to, output
exactly: UNCLEAR

Output:"""


def translate_reply(
    gap: dict,
    candidates: list[CandidateActivity],
    reply_text: str,
    llm_call: Callable[[str], str] | None = None,
) -> str:
    """Returns a string in resolve.py's exact vocabulary, or raises
    NeedsClarificationError. `llm_call` defaults to carbonroom.llm.complete
    but accepts any str->str function -- inject a fake one in tests so
    this is fully testable with zero network calls and zero API key."""
    if llm_call is None:
        llm_call = llm.complete

    prompt = _build_prompt(gap, candidates, reply_text)
    raw = llm_call(prompt).strip()

    if raw.upper() == "UNCLEAR":
        raise NeedsClarificationError(
            f"could not confidently translate {reply_text!r} for gap {gap.get('id')!r}"
        )

    if not _looks_like_a_recognized_format(raw, candidates):
        # The model ignored instructions and returned something off-menu.
        # Treat that exactly like an "UNCLEAR" -- never pass unvalidated
        # model output down into resolve_gap.
        raise NeedsClarificationError(
            f"model returned an unrecognized translation {raw!r} for reply {reply_text!r}"
        )

    return raw


def _looks_like_a_recognized_format(text: str, candidates: list[CandidateActivity]) -> bool:
    lower = text.lower()
    if lower.startswith("exclude:") or lower.startswith("accept:"):
        return True
    if lower in ("approve", "approved", "confirm", "confirmed"):
        return True
    if text.isdigit():
        return True
    if lower.startswith("use "):
        target = text[4:].strip()
        return any(target == c.activity_id for c in candidates)
    return False
