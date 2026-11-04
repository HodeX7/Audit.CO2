"""Turns a human's reply in a gap thread (contracts/CHANGES.md Section 5.4
resolution formats) into activity status updates + a gap resolution.

Supported resolution text, matching the brief exactly:
  "<n>"              -- numeric choice among this gap's candidate activities
  "use <activity_id>" -- same, by id instead of position
  "exclude: <reason>" -- drop the one candidate activity, keep the gap closed
  "accept: <reason>"  -- accept the risk; nothing changes, gap just closes
  "approve" / a checkmark reaction -- send flagged activities back for
                                       re-verification (used for stale-factor
                                       and false-done gaps)

This never auto-resolves anything by itself — every call here is a direct
result of a human's own reply. A gap with no reply just stays OPEN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

_CONFIRM_WORDS = {"approve", "approved", "confirm", "confirmed", "✅", "yes"}


class UnrecognizedResolutionError(ValueError):
    pass


@dataclass
class ResolutionResult:
    gap_status: str                 # 'RESOLVED' | 'ACCEPTED_RISK'
    resolution_text: str
    activity_status_updates: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_gap(
    gap: dict,
    reply_text: str,
    by_handle: str,
    candidate_activity_ids: tuple[str, ...] = (),
) -> ResolutionResult:
    text = reply_text.strip()
    lower = text.lower()

    if lower.startswith("accept:"):
        reason = text.split(":", 1)[1].strip()
        result = ResolutionResult(
            gap_status="ACCEPTED_RISK",
            resolution_text=f"accepted by {by_handle}: {reason}",
        )

    elif lower.startswith("exclude:"):
        reason = text.split(":", 1)[1].strip()
        if len(candidate_activity_ids) != 1:
            raise UnrecognizedResolutionError(
                "'exclude: <reason>' needs exactly one candidate activity for this gap; "
                "for a conflict with multiple candidates, use 'use <activity_id>' or a numeric choice instead."
            )
        target = candidate_activity_ids[0]
        result = ResolutionResult(
            gap_status="RESOLVED",
            resolution_text=f"excluded by {by_handle}: {reason}",
            activity_status_updates={target: "EXCLUDED"},
        )

    elif lower.startswith("use "):
        target = text[4:].strip()
        if target not in candidate_activity_ids:
            raise UnrecognizedResolutionError(
                f"{target!r} is not one of this gap's candidates: {candidate_activity_ids}"
            )
        updates = {aid: ("UNVERIFIED" if aid == target else "EXCLUDED") for aid in candidate_activity_ids}
        result = ResolutionResult(
            gap_status="RESOLVED",
            resolution_text=f"{by_handle} chose {target}",
            activity_status_updates=updates,
        )

    elif text.isdigit():
        idx = int(text) - 1
        if not (0 <= idx < len(candidate_activity_ids)):
            raise UnrecognizedResolutionError(
                f"choice {text!r} is out of range for {len(candidate_activity_ids)} candidates"
            )
        target = candidate_activity_ids[idx]
        updates = {aid: ("UNVERIFIED" if aid == target else "EXCLUDED") for aid in candidate_activity_ids}
        result = ResolutionResult(
            gap_status="RESOLVED",
            resolution_text=f"{by_handle} chose option {text} ({target})",
            activity_status_updates=updates,
        )

    elif lower in _CONFIRM_WORDS:
        # Send flagged activities back through the pipeline so the next
        # Checker run re-verifies them properly, instead of trusting the
        # reaction as proof by itself.
        updates = {aid: "UNVERIFIED" for aid in candidate_activity_ids}
        result = ResolutionResult(
            gap_status="RESOLVED",
            resolution_text=f"approved by {by_handle}",
            activity_status_updates=updates,
        )

    else:
        raise UnrecognizedResolutionError(f"unrecognized resolution reply: {reply_text!r}")

    result.events.append({
        "at": _now_iso(),
        "actor": by_handle,
        "action": "gap_resolved",
        "ref": {
            "gap_id": gap["id"],
            "gap_kind": gap["kind"],
            "resolution": result.resolution_text,
            "activity_status_updates": result.activity_status_updates,
        },
    })
    return result
