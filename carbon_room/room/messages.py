"""Every message the room posts, as a pure function: values in, text out."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from carbon_room.models import (
    AuditCheck,
    CloseSummary,
    DcLine,
    Finding,
    Gap,
    IngestReport,
    Report,
    SourceTag,
)

UPLOAD_HINT: str = "Attach the file to your reply, or put it in data/inbox/ and reply `upload <file name>`."


def t(kg: Decimal | int | None) -> str:
    raise NotImplementedError


def t_value(tco2e: Decimal | int | None) -> str:
    raise NotImplementedError


def pct(p: Decimal | int | None) -> str:
    raise NotImplementedError


def month_label(month: str) -> str:
    raise NotImplementedError


def month_of(close_id: str) -> str:
    raise NotImplementedError


def close_plan(month_label: str, close_id: str, site_names: list[str], factor_set: str) -> str:
    raise NotImplementedError


def handoff_collect(month_label: str, site_names: list[str]) -> str:
    raise NotImplementedError


def handoff_check(month_label: str) -> str:
    raise NotImplementedError


def collector_statement(report: IngestReport) -> str:
    raise NotImplementedError


def gap_root(gap: Gap, finding: Finding | None, owner_display: str, *, fallback_hint: bool = False) -> str:
    raise NotImplementedError


def options_help(gap: Gap) -> str:
    raise NotImplementedError


def already_resolved(gap: Gap) -> str:
    raise NotImplementedError


def old_close_gap(gap: Gap) -> str:
    raise NotImplementedError


def checking() -> str:
    raise NotImplementedError


def outcome_resolved(gap: Gap) -> str:
    raise NotImplementedError


def outcome_open(gap: Gap, reason: str) -> str:
    raise NotImplementedError


def summary_post(month_label: str, summary: CloseSummary, display: Callable[[str], str]) -> str:
    raise NotImplementedError


def dc_line(dc: DcLine) -> str:
    raise NotImplementedError


def total_moved(before: CloseSummary, after: CloseSummary) -> str:
    raise NotImplementedError


def draft(report: Report, month_label: str) -> str:
    raise NotImplementedError


def published(report: Report, approver_display: str, paths: list[str]) -> str:
    raise NotImplementedError


def trace_card(tag: SourceTag, link: str | None) -> str:
    raise NotImplementedError


def audit_result(check: AuditCheck) -> str:
    raise NotImplementedError


def resume_line(month_label: str, phase: str, gaps: list[Gap], display: Callable[[str], str],
                link: Callable[[str], str]) -> str:
    raise NotImplementedError


def budget_warn(agent: str, warn_label: str) -> str:
    raise NotImplementedError


def budget_stopped(agent: str) -> str:
    raise NotImplementedError


def board(month_label: str, summary: CloseSummary, display: Callable[[str], str],
          link: Callable[[str], str]) -> str:
    raise NotImplementedError


def no_close() -> str:
    raise NotImplementedError


def gap_not_found(gap_id: str) -> str:
    raise NotImplementedError


def tag_not_found(tag: str) -> str:
    raise NotImplementedError


def no_reply_needed() -> str:
    raise NotImplementedError


def help_text(reason: str | None = None) -> str:
    raise NotImplementedError
