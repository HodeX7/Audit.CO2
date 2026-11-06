"""Fake core implementing the contracts section 10 story with fake numbers.

The numbers here are fake. They must never appear in the README or the demo script.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import inspect
import threading
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from carbon_room.models import (
    AuditCheck,
    CloseSummary,
    DcLine,
    Finding,
    Gap,
    IngestReport,
    NeedsRoomEvent,
    NotAllowed,
    NotFound,
    Option,
    Report,
    SourceTag,
)

OPENED_AT = "2026-11-06T16:00:00Z"
PUBLISHED_AT = "2026-11-06T17:00:00Z"
SITES = [("hq", "HQ", "lead"), ("warehouse-2", "Warehouse-2", "priya"), ("dc-eu-west", "Data Centre EU-West", "lead")]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]
EXPECTED_SOURCES = ("wh2-elec", "hq-diesel", "dc", "hq-elec")
DC_LINE = DcLine(Decimal("4320"), Decimal("0"), Decimal("1.2"),
                 "Market-based 0 relies on certificates; certificate quality not verified",
                 "UNVERIFIED", "No per-model AI breakdown on the invoice.")


@dataclass
class _Line:
    line: str
    claim: str
    source: str
    site: str
    activity: str
    value: Decimal
    unit: str
    kg: Decimal
    file_name: str
    excerpt: str
    sha: str
    factor_id: str
    version: str
    geography: str
    recompute: str
    state: str = "excluded"
    approver: str | None = None
    message_id: str | None = None


def _line(line, claim, source, site, activity, value, unit, kg, file_name, excerpt, sha, factor_id, version,
          geography, recompute):
    return _Line(line, claim, source, site, activity, Decimal(value), unit, Decimal(kg), file_name, excerpt,
                 sha + "0" * 52, factor_id, version, geography, recompute)


def _ingest_lines() -> list[_Line]:
    return [
        _line("hq-elec", "CL-0004", "hq-elec", "hq", "electricity_kwh", "48300", "kWh", "9660",
              "hq_electricity_2026-10.pdf", "Total consumption: 48300 kWh", "4c1d8e2a9b70",
              "EGRID-2024-CAMX", "2024", "CAMX", "48300 kWh × 0.2 kgCO2e/kWh = 9660 kgCO2e"),
        _line("diesel-A", "CL-0003", "hq-diesel", "hq", "diesel_l", "2000", "L", "5320",
              "hq_diesel_2026-10_inv-4471.eml", "Diesel delivered: 2000 L", "3b7f0c5d1e92",
              "DEFRA-2026-DIESEL", "2026", "UK", "2000 L × 2.66 kgCO2e/L = 5320 kgCO2e"),
        _line("diesel-B", "CL-0002", "hq-diesel", "hq", "diesel_l", "2400", "L", "6384",
              "hq_diesel_2026-10_inv-4471-rev.eml", "Diesel delivered: 2400 L", "2a6e9b4c0d81",
              "DEFRA-2026-DIESEL", "2026", "UK", "2400 L × 2.66 kgCO2e/L = 6384 kgCO2e"),
        _line("wh2-sep", "CL-0005", "wh2-elec", "warehouse-2", "electricity_kwh", "17500", "kWh", "3500",
              "warehouse2_electricity_2026-10.pdf", "Billing period: 1–30 Sep 2026", "5d2f7a1c8e63",
              "DEFRA-2026-UK", "2026", "UK", "17500 kWh × 0.2 kgCO2e/kWh = 3500 kgCO2e"),
        _line("dc", "CL-0001", "dc", "dc-eu-west", "dc_it_kwh", "14400", "kWh", "4320",
              "dc_euwest_cloud_2026-10.json", "it_energy_kwh: 14400", "1e8c3f6a2b05",
              "EMBER-2025-IE", "2025", "IE", "14400 kWh × 0.3 kgCO2e/kWh = 4320 kgCO2e"),
    ]


def _upload_line() -> _Line:
    return _line("wh2-oct", "CL-0010", "wh2-elec", "warehouse-2", "electricity_kwh", "18000", "kWh", "3600",
                 "warehouse2_electricity_2026-10_actual.pdf", "Billing period: 1–31 Oct 2026", "6f4a0e3b9c27",
                 "DEFRA-2026-UK", "2026", "UK", "18000 kWh × 0.2 kgCO2e/kWh = 3600 kgCO2e")


def _scenario_findings(month: str) -> list[Finding]:
    return [
        Finding("F-0000000001", "R4", "PERIOD", ["CL-0005"], "warehouse-2", month, "priya",
                "Warehouse-2 October bill is a September bill",
                ["File name: warehouse2_electricity_2026-10.pdf", "Billing period: 1–30 Sep 2026"],
                [Option("upload", "upload", "Upload the October bill",
                        {"site": "warehouse-2", "month": month, "activity": "electricity_kwh"})], 2, True),
        Finding("F-0000000002", "R2", "CONFLICTING", ["CL-0003", "CL-0002"], "hq", month, "lead",
                "HQ October diesel has two invoices 400 L apart",
                ["Invoice 4471: Diesel delivered: 2000 L", "Invoice 4471-rev: Diesel delivered: 2400 L"],
                [Option("pick A", "pick", "Invoice 4471 — 2,000 L", {"claim_id": "CL-0003"}),
                 Option("pick B", "pick", "Invoice 4471-rev — 2,400 L", {"claim_id": "CL-0002"})], 2, True),
        Finding("F-0000000003", "R3", "STALE", ["CL-0001"], "dc-eu-west", month, "lead",
                "Data centre invoice uses last year's Ember factor",
                ["vendor_factor_ref: Ember 2024 IE", "Locked factor set FS-2026-10 uses Ember 2025"],
                [Option("approve", "approve", "Use the locked Ember 2025 IE factor",
                        {"use_factor_id": "EMBER-2025-IE"}),
                 Option("reject", "reject", "Exclude the cloud line", {})], 2, True),
        Finding("F-0000000004", "R5", "VARIANCE", ["CL-0004"], "hq", month, "lead",
                "HQ October electricity is 38% above September",
                ["September: 35000 kWh", "October: 48300 kWh (+38%)"],
                [Option("approve", "approve", "Accept +38% against September", {}),
                 Option("reject", "reject", "Exclude HQ electricity", {})], 2, True),
    ]


def _r6_finding(month: str) -> Finding:
    return Finding("F-0000000006", "R6", "DATACENTRE", ["CL-0001"], "dc-eu-west", month, "lead",
                   "Data centre invoice has no per-model AI breakdown",
                   ["ai_breakdown: none on the invoice"], [], 2, False)


class _Close:
    def __init__(self, close_id: str, month: str) -> None:
        self.close_id = close_id
        self.month = month
        self.phase = "OPEN"
        self.gaps: dict[str, Gap] = {}
        self.findings: dict[str, Finding] = {}
        self.lines: list[_Line] = []
        self.draft: Report | None = None
        self.checked = False

    def open_gap(self, finding: Finding) -> None:
        gap_id = f"G-{len(self.gaps) + 1}"
        self.gaps[gap_id] = Gap(gap_id, self.close_id, finding.finding_id, finding.rule, finding.kind,
                                finding.title, finding.owner, "OPEN", list(finding.claim_ids),
                                list(finding.options), None, OPENED_AT, None, None, None)
        self.findings[gap_id] = finding

    def open_gaps(self) -> list[Gap]:
        return sorted((g for g in self.gaps.values() if g.status == "OPEN"), key=lambda g: int(g.gap_id[2:]))

    def findings_now(self) -> list[Finding]:
        return [self.findings[g.gap_id] for g in self.open_gaps()] + [_r6_finding(self.month)]

    def set_phase_after_gaps(self) -> None:
        self.phase = "AWAITING_HUMANS" if self.open_gaps() else "CHECKING"


def _api(func):
    """Record, delay, fail, lock and copy, in that order (SPEC-01 rule 13)."""
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {k: v for k, v in bound.arguments.items() if k != "self"}
        self.calls.append((func.__name__, arguments))
        if self.delay > 0:
            time.sleep(self.delay)
        if func.__name__ in self.fail:
            raise self.fail.pop(func.__name__)
        with self._lock:
            return copy.deepcopy(func(self, *args, **kwargs))

    return wrapper


def _needs_message(actor, chat_message_id) -> None:
    if actor.kind == "human" and not chat_message_id:
        raise NeedsRoomEvent("human actions need a chat message id")


class FakeCore:
    def __init__(self, *, delay: float = 0.0) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.delay = delay
        self.fail: dict[str, BaseException] = {}
        self.on_resolve_open: list[Finding] = []
        self.keep_open: set[str] = set()
        self.budget: dict = {}
        self.audit: AuditCheck | None = None
        self._lock = threading.RLock()
        self._closes: dict[str, _Close] = {}
        self._order: list[str] = []

    # helpers (never recorded)
    def _close(self, close_id: str) -> _Close:
        if close_id not in self._closes:
            raise NotFound(f"unknown close: {close_id}")
        return self._closes[close_id]

    @staticmethod
    def _totals(close: _Close) -> tuple[Decimal, Decimal]:
        verified = sum((x.kg for x in close.lines if x.state == "verified"), Decimal(0))
        excluded = sum((x.kg for x in close.lines if x.state == "excluded"), Decimal(0))
        return verified, excluded

    @staticmethod
    def _coverage(verified: Decimal, excluded: Decimal) -> Decimal:
        if verified + excluded == 0:
            return Decimal("0")
        return (verified * 100 / (verified + excluded)).quantize(Decimal("1"), ROUND_HALF_UP)

    @staticmethod
    def _sources_verified(close: _Close) -> int:
        verified = {x.source for x in close.lines if x.state == "verified"}
        return sum(1 for s in EXPECTED_SOURCES if s in verified)

    @_api
    def start_close(self, month, sites, factor_set, actor, chat_message_id):
        _needs_message(actor, chat_message_id)
        n = sum(1 for c in self._closes.values() if c.month == month) + 1
        close_id = f"{month}-v{n}"
        self._closes[close_id] = _Close(close_id, month)
        self._order.append(close_id)
        return close_id

    @_api
    def ingest(self, close_id, actor):
        close = self._close(close_id)
        if not close.lines:
            close.lines = _ingest_lines()
        close.phase = "COLLECTING"
        month_name = MONTH_NAMES[int(close.month.split("-")[1]) - 1]
        return IngestReport(close_id, 9, [f"CL-{i:04d}" for i in range(1, 10)], [],
                            f"All 5 {month_name} sources collected.")

    @_api
    def ingest_file(self, close_id, path, actor, chat_message_id, site=None):
        _needs_message(actor, chat_message_id)
        return ["CL-0010"]

    @_api
    def calculate(self, close_id):
        self._close(close_id).phase = "CALCULATING"
        return []

    @_api
    def check(self, close_id):
        close = self._close(close_id)
        if not close.checked:
            close.checked = True
            for finding in _scenario_findings(close.month):
                close.open_gap(finding)
        close.set_phase_after_gaps()
        return close.findings_now()

    @_api
    def resolve(self, gap_id, action, actor, chat_message_id, payload):
        _needs_message(actor, chat_message_id)
        close = self._closes[self._order[-1]] if self._order else None
        gap = close.gaps.get(gap_id) if close else None
        if gap is None:
            raise NotFound(f"unknown gap: {gap_id}")
        if actor.role is None or not (actor.role == "lead" or actor.id == gap.owner):
            raise NotAllowed(f"only the lead or the gap owner can resolve {gap_id}")
        if gap.status == "RESOLVED":
            raise ValueError(f"gap {gap_id} is already resolved")
        if action not in [o.action for o in gap.options]:
            raise ValueError(f"gap {gap_id} has no {action} option")
        if action == "upload" and not payload.get("path"):
            raise ValueError("upload needs payload['path']")
        if gap_id in self.keep_open:
            return close.findings_now()
        self._apply(close, gap, action, payload, actor, chat_message_id)
        gap.status = "RESOLVED"
        gap.resolved_by = actor.id
        gap.resolved_message_id = chat_message_id
        gap.resolution = {"action": action, "payload": dict(payload)}
        extra, self.on_resolve_open = self.on_resolve_open, []
        for finding in extra:
            close.open_gap(finding)
        close.set_phase_after_gaps()
        return close.findings_now()

    @staticmethod
    def _apply(close: _Close, gap: Gap, action: str, payload: dict, actor, chat_message_id) -> None:
        by_name = {x.line: x for x in close.lines}

        def verify(name: str) -> None:
            line = by_name[name]
            line.state, line.approver, line.message_id = "verified", actor.id, chat_message_id

        if action == "reject":
            return
        if gap.rule == "R4" and action == "upload":
            close.lines.append(_upload_line())
            by_name["wh2-oct"] = close.lines[-1]
            verify("wh2-oct")
            by_name["wh2-sep"].state = "dropped"
        elif gap.rule == "R2" and action == "pick":
            keep = {"CL-0003": "diesel-A", "CL-0002": "diesel-B"}.get(payload.get("claim_id"))
            if keep:
                verify(keep)
                by_name["diesel-B" if keep == "diesel-A" else "diesel-A"].state = "dropped"
        elif gap.rule == "R3" and action == "approve":
            verify("dc")
        elif gap.rule == "R5" and action == "approve":
            verify("hq-elec")

    @_api
    def summary(self, close_id):
        close = self._close(close_id)
        verified, excluded = self._totals(close)
        return CloseSummary(close_id, close.phase, verified, excluded, self._coverage(verified, excluded), 4,
                            self._sources_verified(close), close.open_gaps(), DC_LINE)

    @_api
    def draft_report(self, close_id):
        close = self._close(close_id)
        verified, excluded = self._totals(close)
        coverage = self._coverage(verified, excluded)
        tags = []
        for line in (x for x in close.lines if x.state == "verified"):
            tags.append(SourceTag(f"S-{len(tags) + 1:03d}", line.file_name, 1, line.excerpt, line.sha,
                                  line.activity, line.value, line.unit, line.factor_id, line.version,
                                  line.geography, line.recompute, line.kg, "VERIFIED", line.approver,
                                  line.message_id))
        gaps = [{"gap_id": g.gap_id, "title": g.title, "owner": g.owner} for g in close.open_gaps()]
        conflicts = [d for d in gaps if d["gap_id"] == "G-2"]
        report = Report(close_id, 1, verified / 1000, excluded / 1000, coverage,
                        f"{self._sources_verified(close)} of 4 expected sources verified", gaps, conflicts,
                        ["DEFRA 2026", "EGRID 2024", "EMBER 2025"], DC_LINE, tags,
                        ["Scope 3 not computed: Cat 1 and Cat 6 listed as no data, not zero"], None, None)
        close.draft = report
        close.phase = "DRAFTED"
        return report

    @_api
    def publish(self, close_id, actor, chat_message_id):
        close = self._close(close_id)
        _needs_message(actor, chat_message_id)
        if actor.role != "lead":
            raise NotAllowed("only the lead can publish")
        if close.phase != "DRAFTED":
            raise ValueError("draft the report before publishing")
        close.phase = "PUBLISHED"
        return dataclasses.replace(close.draft, approver=actor.id, published_at=PUBLISHED_AT)

    @_api
    def trace(self, close_id, tag):
        close = self._close(close_id)
        if close.draft is not None:
            for source_tag in close.draft.s_tags:
                if source_tag.tag == tag:
                    return source_tag
        raise NotFound(f"unknown tag: {tag}")

    @_api
    def verify_audit(self, close_id):
        self._close(close_id)
        if self.audit is not None:
            return self.audit
        return AuditCheck(True, len(self.calls), None)

    @_api
    def resume_state(self, close_id):
        close = self._close(close_id)
        return close.phase, close.open_gaps()

    @_api
    def latest_close(self):
        return self._order[-1] if self._order else None

    @_api
    def gap_for_thread(self, thread_root_message_id):
        for close in self._closes.values():
            for gap in close.gaps.values():
                if gap.thread_root_message_id == thread_root_message_id:
                    return gap
        return None

    @_api
    def record_gap_thread(self, close_id, gap_id, message_id):
        close = self._close(close_id)
        gap = close.gaps.get(gap_id)
        if gap is None:
            raise NotFound(f"unknown gap: {gap_id}")
        if not message_id:
            raise ValueError("gap thread message_id is required")
        if gap.thread_root_message_id:
            return None
        for other_close in self._closes.values():
            for other in other_close.gaps.values():
                if other.thread_root_message_id == message_id:
                    raise ValueError(f"Switch thread {message_id!r} is already linked to gap {other.gap_id}")
        gap.thread_root_message_id = message_id
        return None

    @_api
    def budget_usage(self, close_id):
        self._close(close_id)
        return self.budget

    @_api
    def explain(self, close_id, question, actor):
        close = self._close(close_id)
        q = question.lower()
        site = next((s for s in SITES if s[0] in q or s[1].lower() in q), None)
        lines = [x for x in close.lines if x.state == "verified" and (site is None or x.site == site[0])]
        if not lines:
            owner = site[2] if site else "lead"
            return (f"UNKNOWN for {site[0] if site else 'this close'}, because no VERIFIED ledger rows match, "
                    f"owned by {owner}")
        facts = "; ".join(f"{x.claim}: {x.site} {x.value} {x.unit}, {x.kg} kgCO2e, status VERIFIED"
                          for x in lines)
        return "Verified ledger facts: " + facts
