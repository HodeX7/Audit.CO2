"""Extraction with proof.

1. Read each page's text (pdfplumber; plain .txt/.md is one page per form feed).
2. A proposer suggests structured fields, each with a VERBATIM excerpt and a page number:
     cache  -> data/seed/extractions/<sha256>.json (committed, so the demo needs no API key)
     llm    -> carbonroom/llm.py (NVIDIA by default)
     rules  -> carbonroom/ingest/rules.py (label patterns for known layouts; no network)
3. Code verifies every proposed value:
     * the excerpt is found in the document text (whitespace-normalized, case-insensitive);
       the stored excerpt is the full source line(s), and the locator is computed by code
     * the number is in the excerpt and the unit is in the excerpt
     * the site is named in its excerpt (exactly one known site) and the period parses
       from its excerpt to the same YYYY-MM
   Anything that fails is NOT stored as a fact; it becomes an `unverified_claim` gap.
4. Quantities are normalized (carbonroom/ingest/units.py); the original stays in extra_json.

The proposal format (`cr.extraction.v1`) is documented in docs/EXPLAIN_ingestion.md.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from carbonroom import config, llm
from carbonroom.ingest import rules
from carbonroom.ingest.hashing import excerpt_sha256, normalize_ws
from carbonroom.ingest.units import KNOWN_CATEGORIES, Normalized, UnitError, normalize, unit_in_text

PROPOSAL_SCHEMA = "cr.extraction.v1"
CACHE_SCHEMA = "cr.extraction-cache.v1"
TEXT_SUFFIXES = {".txt", ".md"}
PDF_SUFFIXES = {".pdf"}
MIN_EXCERPT_CHARS = 8

# Extra fields we keep per category, and how to check them.
# kind: "number" (value must be a number in the excerpt), "text" (value must be in the excerpt)
CLAIM_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
    "electricity": {"meter_id": {"kind": "text"}},
    "natural_gas": {"meter_id": {"kind": "text"}},
    "diesel": {"delivery_ref": {"kind": "text"}, "delivery_date": {"kind": "text"}},
    "cloud_compute": {
        "pue": {"kind": "number", "required": True},
        "wue_l_per_kwh": {"kind": "number", "unit": "L/kWh"},
        "cloud_region": {"kind": "text"},
    },
}
INSTRUMENT_FIELDS: dict[str, dict[str, Any]] = {
    "certificate_id": {"kind": "text", "required": True},
    "region": {"kind": "text", "required": True},
    "vintage": {"kind": "number", "required": True},
}


# ---------------------------------------------------------------------------
# Page text
# ---------------------------------------------------------------------------


def read_pages(path: str | Path) -> list[str]:
    """Text of each page. Returns [] for formats we can't read without OCR (images)."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in PDF_SUFFIXES:
        import pdfplumber

        try:
            with pdfplumber.open(str(p)) as pdf:
                return [(page.extract_text() or "") for page in pdf.pages]
        except Exception:  # noqa: BLE001 - a corrupt or encrypted PDF is "unreadable", which becomes a gap
            return []
    if suffix in TEXT_SUFFIXES:
        return p.read_text(encoding="utf-8", errors="replace").split("\f")
    return []


def resolve_doc_path(path: str) -> Path:
    """Find a source_docs.path on disk (relative to cwd, then to the repo root)."""
    candidate = Path(path)
    if candidate.exists():
        return candidate
    alt = config.repo_root() / path
    return alt if alt.exists() else candidate


# ---------------------------------------------------------------------------
# Numbers and periods
# ---------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![\d,]*\d)")


def numbers_in(text: str) -> list[Decimal]:
    out = []
    for m in _NUM.finditer(text):
        try:
            out.append(Decimal(m.group(1).replace(",", "") + (m.group(2) or "")))
        except InvalidOperation:  # pragma: no cover
            continue
    return out


def to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"\d+(?:\.\d+)?", text)
    return Decimal(text) if match else None


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_NAME = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(?:(\d{1,2}),?\s+)?(\d{4})\b",
    re.IGNORECASE,
)
_ISO_MONTH = re.compile(r"\b(\d{4})-(0[1-9]|1[0-2])(?:-\d{2})?\b")
_US_DATE = re.compile(r"\b(0?[1-9]|1[0-2])/(\d{1,2})/(\d{4})\b")


def periods_in_text(text: str) -> set[str]:
    found: set[str] = set()
    for m in _MONTH_NAME.finditer(text):
        found.add(f"{int(m.group(3)):04d}-{_MONTHS[m.group(1).lower()]:02d}")
    for m in _ISO_MONTH.finditer(text):
        found.add(f"{m.group(1)}-{m.group(2)}")
    for m in _US_DATE.finditer(text):
        found.add(f"{m.group(3)}-{int(m.group(1)):02d}")
    return found


def parse_period(text: str) -> str | None:
    """'Service period: October 1, 2026 - October 31, 2026' -> '2026-10'. Ambiguous -> None."""
    found = periods_in_text(text)
    return found.pop() if len(found) == 1 else None


# ---------------------------------------------------------------------------
# Finding an excerpt in the document
# ---------------------------------------------------------------------------


@dataclass
class ExcerptMatch:
    page: int  # 1-based
    line_start: int  # 1-based
    line_end: int
    excerpt: str  # the full source line(s), whitespace-normalized (what the ledger stores)
    span: str  # the matched text itself, whitespace-normalized

    @property
    def locator(self) -> str:
        if self.line_start == self.line_end:
            return f"page={self.page};line={self.line_start}"
        return f"page={self.page};lines={self.line_start}-{self.line_end}"


def _page_index(page_text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Normalized page string plus (start, end, normalized line) for every non-empty line."""
    lines = []
    parts = []
    pos = 0
    for raw in page_text.split("\n"):
        norm = normalize_ws(raw)
        if not norm:
            continue
        if parts:
            pos += 1  # the joining space
        lines.append((pos, pos + len(norm), norm))
        parts.append(norm)
        pos += len(norm)
    return " ".join(parts), lines


def find_excerpt(pages: list[str], excerpt: str, page_hint: int | None = None) -> ExcerptMatch | None:
    """Locate `excerpt` in the document. The hinted page is searched first; the locator always
    reports where code actually found it (never the proposer's claim)."""
    needle = normalize_ws(str(excerpt or "")).strip(" \"'")
    if len(needle) < MIN_EXCERPT_CHARS:
        return None
    order = list(range(len(pages)))
    if page_hint and 1 <= int(page_hint) <= len(pages):
        order.remove(int(page_hint) - 1)
        order.insert(0, int(page_hint) - 1)
    for idx in order:
        joined, lines = _page_index(pages[idx])
        hay = joined.casefold()
        at = hay.find(needle.casefold())
        if at < 0:
            continue
        if len(hay) != len(joined):
            # casefolding changed the length (rare non-ASCII text): fall back to whole lines
            for n, (_, _, text) in enumerate(lines, start=1):
                if needle.casefold() in text.casefold():
                    return ExcerptMatch(idx + 1, n, n, text, text)
            continue
        end = at + len(needle)
        covered = [ln for ln in lines if ln[0] < end and ln[1] > at]
        if not covered:
            continue
        first = lines.index(covered[0]) + 1
        last = lines.index(covered[-1]) + 1
        # line numbers are counted over non-empty lines on the page
        return ExcerptMatch(
            page=idx + 1,
            line_start=first,
            line_end=last,
            excerpt=" ".join(ln[2] for ln in covered),
            span=joined[at:end],
        )
    return None


def excerpt_in_document(path: str | Path, excerpt: str, page: int | None = None) -> bool:
    """Re-check helper for the checker: is this stored excerpt still on that page of the file?"""
    pages = read_pages(resolve_doc_path(str(path)))
    if page is None:
        return find_excerpt(pages, excerpt) is not None
    if not 1 <= page <= len(pages):
        return False
    return find_excerpt([pages[page - 1]], excerpt) is not None


def locator_page(locator: str) -> int | None:
    m = re.search(r"page=(\d+)", locator or "")
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Proposers and the cache
# ---------------------------------------------------------------------------


@dataclass
class Proposed:
    proposal: dict[str, Any]
    proposer: str
    from_cache: bool
    notes: list[str] = field(default_factory=list)


def _cache_dirs() -> list[Path]:
    return [config.extraction_cache_dir(), config.store_dir() / "extractions"]


def load_cached(sha256: str) -> dict[str, Any] | None:
    for directory in _cache_dirs():
        path = directory / f"{sha256}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema") == CACHE_SCHEMA and data.get("sha256") == sha256:
                return data
    return None


def save_cache(sha256: str, source_path: Path, proposal: dict[str, Any], proposer: str) -> Path:
    """Seed documents cache into data/seed/extractions (committed); others into data/store."""
    try:
        source_path.resolve().relative_to(config.seed_dir().resolve())
        directory = config.extraction_cache_dir()
    except ValueError:
        directory = config.store_dir() / "extractions"
    directory.mkdir(parents=True, exist_ok=True)
    out = directory / f"{sha256}.json"
    payload = {
        "schema": CACHE_SCHEMA,
        "sha256": sha256,
        "file": source_path.name,
        "proposer": proposer,
        "proposal": proposal,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


LLM_SYSTEM = """You extract emissions activity data from ONE business document: a utility bill,
fuel invoice, cloud invoice or renewable energy certificate (REC).
Return ONLY a JSON object, no prose, in exactly this shape:
{
  "schema": "cr.extraction.v1",
  "doc_kind": "utility_bill | fuel_invoice | cloud_invoice | rec_certificate | other",
  "doc_ref": {"value": "<document number>", "excerpt": "<line>", "page": 1} or null,
  "replaces_ref": {"value": "<number of the document this one corrects/replaces>", "excerpt": "<line>", "page": 1} or null,
  "site": {"value": "<site/location name as printed>", "excerpt": "<line naming the site>", "page": 1},
  "period": {"value": "YYYY-MM", "excerpt": "<line stating the service/billing/delivery/consumption period>", "page": 1},
  "claims": [
    {"category": "electricity | natural_gas | diesel | cloud_compute",
     "quantity": "<number exactly as printed>", "unit": "<unit exactly as printed>",
     "excerpt": "<line containing the quantity and unit>", "page": 1,
     "fields": {"<name>": {"value": "<as printed>", "excerpt": "<line>", "page": 1}}}
  ],
  "instruments": [
    {"kind": "REC", "mwh": "<number as printed>", "unit": "MWh", "excerpt": "<line>", "page": 1,
     "fields": {"certificate_id": {...}, "region": {...}, "vintage": {...}}}
  ]
}
Rules:
- Copy every excerpt VERBATIM from ONE line of the document text. It must contain the value.
- Never calculate, convert, round or guess. If something is not printed, leave it out.
- "page" is the page number (=== PAGE n ===) where the excerpt appears.
- Claims are only total energy/fuel consumed: electricity used, natural gas used, fuel delivered,
  IT equipment energy for a cloud account. Ignore money, demand (kW), meter reads and history.
- Field names: diesel -> delivery_ref, delivery_date; cloud_compute -> pue, wue_l_per_kwh, cloud_region;
  electricity/natural_gas -> meter_id. REC -> certificate_id, region (generation region), vintage (year).
- "site" is WHERE the energy was used, never the customer company name: the service location on a
  utility bill, the delivery location on a fuel invoice, the region line (e.g. "Region: ...") on a cloud
  invoice, and the load it is claimed against on an REC."""


def llm_propose(file_name: str, pages: list[str], model: str | None = None,
                attempts: int | None = None) -> tuple[dict[str, Any], str]:
    body = "\n\n".join(f"=== PAGE {i} ===\n{text}" for i, text in enumerate(pages, start=1))
    messages = [
        {"role": "system", "content": LLM_SYSTEM},
        {"role": "user", "content": f"File name: {file_name}\n\n{body}"},
    ]
    proposal, p = llm.chat_json(messages, model=model, max_tokens=3000, attempts=attempts)  # room for reasoning
    proposal.setdefault("schema", PROPOSAL_SCHEMA)
    return proposal, p.label


def propose(
    path: Path,
    pages: list[str],
    sha256: str,
    *,
    mode: str = "auto",
    refresh: bool = False,
) -> Proposed:
    """mode: auto (cache -> llm if a key is set -> rules), llm, rules."""
    if mode not in ("auto", "llm", "rules"):
        raise ValueError(f"unknown proposer mode {mode!r}")
    if not refresh:
        cached = load_cached(sha256)
        if cached:
            return Proposed(cached["proposal"], f"cache:{cached['proposer']}", True)
    notes: list[str] = []
    if mode in ("auto", "llm"):
        if llm.is_configured():
            try:
                proposal, label = llm_propose(path.name, pages)
                save_cache(sha256, path, proposal, label)
                return Proposed(proposal, label, False, notes)
            except (llm.LLMError, json.JSONDecodeError) as exc:
                if mode == "llm":
                    raise
                notes.append(f"LLM proposal failed ({exc}); used the rules proposer instead")
        elif mode == "llm":
            raise llm.LLMNotConfigured("no LLM key is configured (see .env.example)")
    proposal = rules.propose(pages)
    save_cache(sha256, path, proposal, rules.PROPOSER)
    return Proposed(proposal, rules.PROPOSER, False, notes)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass
class VerifiedField:
    name: str
    value: str
    excerpt: str
    locator: str
    excerpt_sha256: str

    def evidence(self) -> dict[str, str]:
        return {"excerpt": self.excerpt, "locator": self.locator, "excerpt_sha256": self.excerpt_sha256}


@dataclass
class Failure:
    scope: str  # doc | claim | field | instrument
    reason: str
    index: int | None = None
    field: str | None = None
    proposed: dict[str, Any] | None = None

    @property
    def key(self) -> str:
        parts = [self.scope]
        if self.index is not None:
            parts.append(str(self.index))
        if self.field:
            parts.append(self.field)
        if self.scope == "doc":  # several document-level problems must not collapse into one gap
            parts.append(excerpt_sha256(self.reason)[:8])
        return ":".join(parts)


@dataclass
class VerifiedClaim:
    index: int
    category: str
    normalized: Normalized
    excerpt: str
    locator: str
    excerpt_sha256: str
    site_id: str
    period: str
    fields: dict[str, VerifiedField]
    unverified_fields: list[str]


@dataclass
class VerifiedInstrument:
    index: int
    kind: str
    normalized: Normalized
    excerpt: str
    locator: str
    excerpt_sha256: str
    site_id: str | None
    period: str
    fields: dict[str, VerifiedField]
    unverified_fields: list[str]


@dataclass
class Extraction:
    proposer: str
    doc_kind: str | None
    doc_ref: VerifiedField | None
    replaces_ref: VerifiedField | None
    site_id: str | None
    site_evidence: VerifiedField | None
    period: str | None
    period_evidence: VerifiedField | None
    claims: list[VerifiedClaim]
    instruments: list[VerifiedInstrument]
    failures: list[Failure]
    notes: list[str] = field(default_factory=list)


SiteMatcher = Callable[[str], list[str]]


def site_matcher_for(conn: sqlite3.Connection) -> SiteMatcher:
    from carbonroom.ledger import db

    return lambda text: db.match_sites(conn, text)


def _verify_value(
    pages: list[str], name: str, obj: Any, kind: str = "text", unit: str | None = None
) -> tuple[VerifiedField | None, str | None]:
    if not isinstance(obj, dict):
        return None, "not proposed"
    value = obj.get("value")
    if value is None or str(value).strip() == "":
        return None, "no value proposed"
    match = find_excerpt(pages, obj.get("excerpt", ""), obj.get("page"))
    if match is None:
        return None, f"excerpt {str(obj.get('excerpt'))[:80]!r} was not found in the document"
    if kind == "number":
        number = to_decimal(value)
        if number is None:
            return None, f"value {value!r} is not a number"
        if number not in numbers_in(match.span):
            return None, f"{value} does not appear in the excerpt"
        value_text = format(number.normalize(), "f")
    else:
        value_text = normalize_ws(str(value))
        if value_text.casefold() not in match.span.casefold():
            return None, f"{value_text!r} does not appear in the excerpt"
    if unit and not unit_in_text(unit, match.span):
        return None, f"unit {unit} does not appear in the excerpt"
    return (
        VerifiedField(name, value_text, match.excerpt, match.locator, excerpt_sha256(match.excerpt)),
        None,
    )


def _verify_site(pages, obj, match_sites: SiteMatcher) -> tuple[str | None, VerifiedField | None, str | None]:
    if not isinstance(obj, dict) or not obj.get("excerpt"):
        return None, None, "no site evidence proposed"
    match = find_excerpt(pages, obj.get("excerpt", ""), obj.get("page"))
    if match is None:
        return None, None, "site excerpt was not found in the document"
    in_excerpt = match_sites(match.span) or match_sites(match.excerpt)
    if len(in_excerpt) != 1:
        return None, None, f"site excerpt names {len(in_excerpt)} known sites (need exactly 1)"
    site_id = in_excerpt[0]
    value = str(obj.get("value") or "")
    if value and match_sites(value) and site_id not in match_sites(value):
        return None, None, f"proposed site {value!r} disagrees with the excerpt"
    evidence = VerifiedField("site", site_id, match.excerpt, match.locator, excerpt_sha256(match.excerpt))
    return site_id, evidence, None


def site_named_in_document(pages: list[str], match_sites: SiteMatcher) -> tuple[str, VerifiedField] | None:
    """If the whole document names exactly ONE known site, return it with the first line naming it.

    Used only when the proposer pointed at a line that names no site (e.g. "Customer: Brightwell
    Manufacturing"). Code finds the evidence itself; a document naming two sites gets no fallback.
    """
    first_line: dict[str, tuple[int, int, str]] = {}
    for page_no, text in enumerate(pages, start=1):
        _, lines = _page_index(text)
        for line_no, (_, _, line) in enumerate(lines, start=1):
            for site_id in match_sites(line):
                first_line.setdefault(site_id, (page_no, line_no, line))
    if len(first_line) != 1:
        return None
    site_id, (page_no, line_no, line) = next(iter(first_line.items()))
    return site_id, VerifiedField("site", site_id, line, f"page={page_no};line={line_no}", excerpt_sha256(line))


_SITE_FALLBACK_REASONS = ("no site evidence proposed", "site excerpt was not found", "site excerpt names 0 known")


def _verify_period(pages, obj) -> tuple[str | None, VerifiedField | None, str | None]:
    if not isinstance(obj, dict) or not obj.get("excerpt"):
        return None, None, "no period evidence proposed"
    match = find_excerpt(pages, obj.get("excerpt", ""), obj.get("page"))
    if match is None:
        return None, None, "period excerpt was not found in the document"
    from_excerpt = parse_period(match.span) or parse_period(match.excerpt)
    if from_excerpt is None:
        return None, None, "the period excerpt does not name exactly one month"
    proposed = str(obj.get("value") or "")
    proposed_period = proposed if re.fullmatch(r"\d{4}-\d{2}", proposed) else parse_period(proposed)
    if proposed_period and proposed_period != from_excerpt:
        return None, None, f"proposed period {proposed} disagrees with the excerpt ({from_excerpt})"
    evidence = VerifiedField("period", from_excerpt, match.excerpt, match.locator, excerpt_sha256(match.excerpt))
    return from_excerpt, evidence, None


def _verify_fields(pages, spec: dict[str, dict[str, Any]], proposed: dict[str, Any], scope: str, index: int,
                   failures: list[Failure]) -> tuple[dict[str, VerifiedField], list[str]]:
    verified: dict[str, VerifiedField] = {}
    unverified: list[str] = []
    for name, rule in spec.items():
        obj = (proposed or {}).get(name)
        if obj is None and not rule.get("required"):
            continue
        vf, reason = _verify_value(pages, name, obj, rule.get("kind", "text"), rule.get("unit"))
        if vf:
            verified[name] = vf
        else:
            unverified.append(name)
            failures.append(Failure("field", f"{name}: {reason}", index=index, field=name,
                                    proposed={"scope": scope, "value": obj}))
    return verified, unverified


def _verify_quantity(pages, item: dict[str, Any], category: str) -> tuple[tuple | None, str | None]:
    quantity = to_decimal(item.get("quantity", item.get("mwh")))
    unit = str(item.get("unit") or "")
    if quantity is None:
        return None, f"quantity {item.get('quantity', item.get('mwh'))!r} is not a plain number"
    match = find_excerpt(pages, item.get("excerpt", ""), item.get("page"))
    if match is None:
        return None, f"excerpt {str(item.get('excerpt'))[:80]!r} was not found in the document"
    if quantity not in numbers_in(match.span):
        return None, f"quantity {item.get('quantity', item.get('mwh'))} does not appear in the excerpt"
    if not unit or not unit_in_text(unit, match.span):
        return None, f"unit {unit!r} does not appear in the excerpt"
    try:
        normalized = normalize(category, quantity, unit)
    except UnitError as exc:
        return None, str(exc)
    return (normalized, match), None


def verify(proposal: dict[str, Any], pages: list[str], match_sites: SiteMatcher, proposer: str = "") -> Extraction:
    """Accept only what the document itself proves. Never raises on a bad proposal."""
    failures: list[Failure] = []
    if not isinstance(proposal, dict):
        proposal = {}
    if not pages or not any(p.strip() for p in pages):
        failures.append(Failure("doc", "no readable text (a scan or photo needs a text PDF)"))
    doc_kind = proposal.get("doc_kind")
    doc_ref, _ = _verify_value(pages, "doc_ref", proposal.get("doc_ref"))
    replaces_ref = None
    if proposal.get("replaces_ref"):
        replaces_ref, reason = _verify_value(pages, "replaces_ref", proposal.get("replaces_ref"))
        if replaces_ref is None:
            failures.append(Failure("doc", f"replaces_ref: {reason}"))
    site_id, site_ev, site_reason = _verify_site(pages, proposal.get("site"), match_sites)
    notes: list[str] = []
    if site_id is None and site_reason and site_reason.startswith(_SITE_FALLBACK_REASONS):
        found = site_named_in_document(pages, match_sites)
        if found:
            site_id, site_ev = found
            notes.append(f"site resolved by code from the document ({site_reason}): {site_ev.excerpt}")
    period, period_ev, period_reason = _verify_period(pages, proposal.get("period"))

    claims: list[VerifiedClaim] = []
    seen: set[tuple[str, str]] = set()
    for i, item in enumerate(proposal.get("claims") or []):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "")
        if category not in KNOWN_CATEGORIES:
            failures.append(Failure("claim", f"unknown category {category!r}", index=i, proposed=item))
            continue
        result, reason = _verify_quantity(pages, item, category)
        if result is None:
            failures.append(Failure("claim", f"{category}: {reason}", index=i, proposed=item))
            continue
        normalized, match = result
        c_site, c_period = site_id, period
        if item.get("site"):
            c_site, _, reason = _verify_site(pages, item["site"], match_sites)
            if c_site is None:
                failures.append(Failure("claim", f"{category}: site {reason}", index=i, proposed=item))
                continue
        if item.get("period"):
            c_period, _, reason = _verify_period(pages, item["period"])
            if c_period is None:
                failures.append(Failure("claim", f"{category}: period {reason}", index=i, proposed=item))
                continue
        if c_site is None or c_period is None:
            failures.append(Failure("claim", f"{category}: site or period could not be verified", index=i,
                                    proposed=item))
            continue
        key = (category, match.excerpt)
        if key in seen:
            continue
        seen.add(key)
        fields, unverified = _verify_fields(pages, CLAIM_FIELDS.get(category, {}), item.get("fields") or {},
                                            "claim", i, failures)
        claims.append(VerifiedClaim(i, category, normalized, match.excerpt, match.locator,
                                    excerpt_sha256(match.excerpt), c_site, c_period, fields, unverified))

    instruments: list[VerifiedInstrument] = []
    for j, item in enumerate(proposal.get("instruments") or []):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").upper()
        if kind not in ("REC", "PPA"):
            failures.append(Failure("instrument", f"unknown instrument kind {kind!r}", index=j, proposed=item))
            continue
        result, reason = _verify_quantity(pages, item, "rec_mwh")
        if result is None:
            failures.append(Failure("instrument", f"{kind}: {reason}", index=j, proposed=item))
            continue
        normalized, match = result
        if period is None:
            failures.append(Failure("instrument", f"{kind}: the consumption period could not be verified",
                                    index=j, proposed=item))
            continue
        fields, unverified = _verify_fields(pages, INSTRUMENT_FIELDS, item.get("fields") or {},
                                            "instrument", j, failures)
        instruments.append(VerifiedInstrument(j, kind, normalized, match.excerpt, match.locator,
                                              excerpt_sha256(match.excerpt), site_id, period, fields, unverified))

    if (proposal.get("claims") or proposal.get("instruments")) and (site_id is None or period is None):
        reasons = [r for r in (site_reason and f"site: {site_reason}", period_reason and f"period: {period_reason}") if r]
        failures.append(Failure("doc", "; ".join(reasons)))
    if not proposal.get("claims") and not proposal.get("instruments") and pages and any(p.strip() for p in pages):
        failures.append(Failure("doc", "no quantity could be extracted from this document"))

    return Extraction(
        proposer=proposer,
        doc_kind=doc_kind if isinstance(doc_kind, str) else None,
        doc_ref=doc_ref,
        replaces_ref=replaces_ref,
        site_id=site_id,
        site_evidence=site_ev,
        period=period,
        period_evidence=period_ev,
        claims=claims,
        instruments=instruments,
        failures=failures,
        notes=notes,
    )
