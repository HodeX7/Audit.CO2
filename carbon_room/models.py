"""Frozen cross-team types from Contracts section 2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from decimal import Decimal
from types import UnionType
from typing import Any, Literal, TypeVar, Union, get_args, get_origin, get_type_hints

Status = Literal["VERIFIED", "UNVERIFIED", "CONFLICTING", "STALE", "MISSING"]
Phase = Literal["OPEN", "COLLECTING", "CALCULATING", "CHECKING", "AWAITING_HUMANS", "RECHECKING", "DRAFTED", "PUBLISHED"]
SourceKind = Literal["utility_pdf", "email_invoice", "drive_csv", "cloud_invoice"]
Activity = Literal["electricity_kwh", "diesel_l", "dc_it_kwh"]


@dataclass(frozen=True)
class Actor:
    kind: Literal["human", "agent", "system"]
    id: str
    name: str
    role: str | None = None


@dataclass
class Source:
    source_doc_id: str; close_id: str; site: str | None; kind: SourceKind
    file_name: str; stored_path: str; sha256: str; page_count: int; raw_text: str
    period_start: str | None; period_end: str | None
    extract_status: Literal["OK", "FAILED"]; extract_error: str | None


@dataclass
class Claim:
    claim_id: str; close_id: str; site: str; month: str; activity: Activity
    value: Decimal; unit: str; scope: Literal["1", "2", "3", "DC"]
    source_doc_id: str; source_excerpt: str; source_sha256: str; source_page: int
    factor_id: str | None; factor_version: str | None
    status: Status; extracted_by: str; checked_by: str | None; superseded_by: str | None
    attributes: dict = field(default_factory=dict)


@dataclass
class Calculation:
    calc_id: str; claim_id: str; factor_id: str; factor_version: str
    activity_value: Decimal; activity_unit: str; factor_value: Decimal; factor_unit: str
    kgco2e: Decimal; formula: str
    basis: Literal["location", "market"] | None


@dataclass
class Option:
    key: str; action: Literal["pick", "approve", "reject", "upload"]; label: str
    params: dict = field(default_factory=dict)


@dataclass
class Finding:
    finding_id: str; rule: Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    kind: Literal["MISSING", "CONFLICTING", "STALE", "PERIOD", "VARIANCE", "DATACENTRE", "FINANCE"]
    claim_ids: list[str]; site: str; month: str; owner: str; title: str
    evidence: list[str]; options: list[Option]; tier: Literal[1, 2, 3]; blocking: bool


@dataclass
class Gap:
    gap_id: str; close_id: str; finding_id: str; rule: str; kind: str; title: str
    owner: str; status: Literal["OPEN", "RESOLVED"]; claim_ids: list[str]; options: list[Option]
    thread_root_message_id: str | None; opened_at: str; resolved_by: str | None
    resolved_message_id: str | None; resolution: dict | None


@dataclass
class IngestReport:
    close_id: str; sources_seen: int; claims_created: list[str]; failed_sources: list[str]; statement: str


@dataclass
class DcLine:
    location_kgco2e: Decimal | None; market_kgco2e: Decimal | None; pue: Decimal | None
    rec_flag: str; ai_line_status: Literal["UNVERIFIED"]; note: str


@dataclass
class CloseSummary:
    close_id: str; phase: Phase; verified_kgco2e: Decimal; excluded_kgco2e: Decimal; coverage_pct: Decimal
    sources_expected: int; sources_verified: int; open_gaps: list[Gap]; dc_line: DcLine | None


@dataclass
class SourceTag:
    tag: str; file_name: str; page: int; excerpt: str; sha256: str; activity: str; value: Decimal; unit: str
    factor_id: str; factor_version: str; geography: str; recompute: str; kgco2e: Decimal; status: Status
    approver: str | None; chat_message_id: str | None


@dataclass
class Report:
    close_id: str; version: int; verified_total_tCO2e: Decimal; unverified_excluded_tCO2e: Decimal
    coverage_pct: Decimal; source_coverage: str; gaps: list[dict]; conflicts: list[dict]; factor_versions: list[str]
    datacentre_line: DcLine | None; s_tags: list[SourceTag]; compliance_flags: list[str]
    approver: str | None; published_at: str | None


@dataclass
class AuditCheck:
    ok: bool; events: int; first_bad_event_id: int | None


class CarbonRoomError(Exception):
    """Base error for the contract-compatible API."""


class NeedsRoomEvent(CarbonRoomError):
    """A human action was attempted without its Switch message id."""


class NotAllowed(CarbonRoomError):
    """The caller is not allowed to take this action."""


class LockHeld(CarbonRoomError):
    """A claim lock belongs to another actor."""


class BudgetExceeded(CarbonRoomError):
    """An agent reached its close-level token budget."""


class NotFound(CarbonRoomError):
    """The requested contract object does not exist."""


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {key: _encode(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def to_dict(value: Any) -> dict[str, Any]:
    """Convert a contract dataclass to JSON-ready data, preserving Decimal precision as text."""
    if not is_dataclass(value):
        raise TypeError("to_dict expects a contract dataclass")
    return _encode(value)


T = TypeVar("T")


def _decode(value: Any, annotation: Any) -> Any:
    if value is None:
        return None
    if annotation is Decimal:
        return Decimal(str(value))
    origin = get_origin(annotation)
    if origin is list:
        return [_decode(item, get_args(annotation)[0]) for item in value]
    if origin is dict:
        return value
    if origin in (Union, UnionType):
        for choice in get_args(annotation):
            if choice is type(None):
                continue
            try:
                return _decode(value, choice)
            except (TypeError, ValueError):
                pass
        return value
    if isinstance(annotation, type) and is_dataclass(annotation):
        return from_dict(annotation, value)
    return value


def from_dict(cls: type[T], value: dict[str, Any]) -> T:
    """Rebuild a contract dataclass from JSON-ready data made by :func:`to_dict`."""
    hints = get_type_hints(cls)
    return cls(**{item.name: _decode(value.get(item.name), hints[item.name]) for item in fields(cls)})
