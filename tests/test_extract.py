"""Excerpt verification: an LLM (or rules) proposal is accepted only if the document proves it."""

from __future__ import annotations

from decimal import Decimal

import pytest

from carbonroom.ingest import extract
from carbonroom.ingest.hashing import excerpt_sha256

PAGES = [
    "Cedar Mesa Power & Light\nELECTRICITY BILL\nBill number: ELB-AUS-2610\n"
    "Service location: Austin Plant, 4100 Foundry Row, Austin, TX\n"
    "Service period: October 1, 2026 - October 31, 2026\nTotal energy used this period: 191,300 kWh\n"
    "Peak demand: 412 kW",
    "Page two\nMeter: CMPL-M-77120\nAmount due: $17,599.60",
]


def matcher(text: str) -> list[str]:
    found = []
    if "austin plant" in text.lower():
        found.append("austin")
    if "reno office" in text.lower():
        found.append("reno")
    return found


def good_proposal(**claim_overrides):
    claim = {"category": "electricity", "quantity": "191,300", "unit": "kWh",
             "excerpt": "Total energy used this period: 191,300 kWh", "page": 1}
    claim.update(claim_overrides)
    return {
        "doc_kind": "utility_bill",
        "doc_ref": {"value": "ELB-AUS-2610", "excerpt": "Bill number: ELB-AUS-2610", "page": 1},
        "site": {"value": "Austin Plant", "excerpt": "Service location: Austin Plant, 4100 Foundry Row", "page": 1},
        "period": {"value": "2026-10", "excerpt": "Service period: October 1, 2026 - October 31, 2026", "page": 1},
        "claims": [claim],
    }


# --- finding excerpts ---------------------------------------------------------------------------

def test_excerpt_found_despite_whitespace_and_case():
    m = extract.find_excerpt(PAGES, "total   ENERGY used this period:\n191,300 kWh", page_hint=1)
    assert m is not None
    assert m.page == 1 and m.locator == "page=1;line=6"
    assert m.excerpt == "Total energy used this period: 191,300 kWh"  # stored text comes from the document


def test_partial_excerpt_stores_the_full_source_line():
    m = extract.find_excerpt(PAGES, "191,300 kWh")
    assert m.excerpt == "Total energy used this period: 191,300 kWh" and m.span == "191,300 kWh"


def test_locator_is_where_code_found_it_not_the_proposed_page():
    m = extract.find_excerpt(PAGES, "Meter: CMPL-M-77120", page_hint=1)
    assert m.page == 2 and m.locator == "page=2;line=2"


def test_missing_or_tiny_excerpts_are_rejected():
    assert extract.find_excerpt(PAGES, "Total energy used this period: 196,800 kWh") is None
    assert extract.find_excerpt(PAGES, "kWh") is None  # too short to be evidence


def test_numbers_and_periods():
    assert extract.numbers_in("Total: 1,892.7 L and 14.62 MWh, 38,200 kWh") == [
        Decimal("1892.7"), Decimal("14.62"), Decimal("38200")]
    assert extract.parse_period("Service period: October 1, 2026 - October 31, 2026") == "2026-10"
    assert extract.parse_period("Billing period: Sept 2026") == "2026-09"
    assert extract.parse_period("Period 2026-10") == "2026-10"
    assert extract.parse_period("10/14/2026") == "2026-10"
    assert extract.parse_period("September 15, 2026 - October 14, 2026") is None  # spans two months


# --- verification -------------------------------------------------------------------------------

def test_good_proposal_passes():
    ex = extract.verify(good_proposal(), PAGES, matcher, "test")
    assert ex.failures == []
    assert ex.site_id == "austin" and ex.period == "2026-10" and ex.doc_ref.value == "ELB-AUS-2610"
    (claim,) = ex.claims
    assert claim.normalized.quantity == Decimal("191300") and claim.normalized.unit == "kWh"
    assert claim.excerpt_sha256 == excerpt_sha256("Total energy used this period: 191,300 kWh")


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"quantity": "196,800"}, "does not appear in the excerpt"),  # number not in the excerpt
        ({"excerpt": "Total energy used this period: 196,800 kWh"}, "was not found"),  # invented excerpt
        ({"unit": "MWh"}, "unit"),  # unit not in the excerpt
        ({"category": "steam"}, "unknown category"),
        ({"quantity": "about 191k"}, "not a plain number"),
        ({"excerpt": "Peak demand: 412 kW", "quantity": "412", "unit": "kW"}, "unit"),
    ],
)
def test_bad_claims_are_rejected_not_stored(override, reason):
    ex = extract.verify(good_proposal(**override), PAGES, matcher, "test")
    assert ex.claims == []
    assert any(reason in f.reason for f in ex.failures), [f.reason for f in ex.failures]


def test_wrong_site_or_period_rejects_the_claim():
    p = good_proposal()
    p["site"] = {"value": "Reno Office", "excerpt": "Service location: Austin Plant, 4100 Foundry Row", "page": 1}
    ex = extract.verify(p, PAGES, matcher)
    assert ex.claims == [] and ex.site_id is None
    p = good_proposal()
    p["period"]["value"] = "2026-09"
    ex = extract.verify(p, PAGES, matcher)
    assert ex.claims == [] and any("disagrees" in f.reason for f in ex.failures)


def test_empty_or_garbage_proposal_never_raises():
    ex = extract.verify({}, PAGES, matcher)
    assert ex.claims == [] and any("no quantity" in f.reason for f in ex.failures)
    ex = extract.verify("not a dict", [], matcher)  # type: ignore[arg-type]
    assert any("no readable text" in f.reason for f in ex.failures)


def test_cloud_fields_are_verified_individually():
    pages = ["Nimbus Cloud, Inc.\nBilling period: October 2026\nRegion: us-east-va (Virginia)\n"
             "IT equipment energy attributed to this account: 38,200 kWh\n"
             "Power usage effectiveness (PUE), facility average: 1.35\nWater usage effectiveness (WUE): 0.42 L/kWh"]
    cloud_matcher = lambda t: ["nimbus-cloud"] if "us-east-va" in t or "nimbus cloud" in t.lower() else []  # noqa: E731
    proposal = {
        "site": {"value": "us-east-va", "excerpt": "Region: us-east-va (Virginia)", "page": 1},
        "period": {"value": "2026-10", "excerpt": "Billing period: October 2026", "page": 1},
        "claims": [{
            "category": "cloud_compute", "quantity": "38,200", "unit": "kWh", "page": 1,
            "excerpt": "IT equipment energy attributed to this account: 38,200 kWh",
            "fields": {
                "pue": {"value": "1.53", "excerpt": "Power usage effectiveness (PUE), facility average: 1.35"},
                "wue_l_per_kwh": {"value": "0.42", "excerpt": "Water usage effectiveness (WUE): 0.42 L/kWh"},
            },
        }],
    }
    ex = extract.verify(proposal, pages, cloud_matcher)
    (claim,) = ex.claims  # the IT kWh is proven, so the claim is kept...
    assert "wue_l_per_kwh" in claim.fields and claim.fields["wue_l_per_kwh"].value == "0.42"
    assert claim.unverified_fields == ["pue"]  # ...but the transposed PUE is not
    assert any(f.scope == "field" and f.field == "pue" for f in ex.failures)


def test_site_line_pointing_at_the_customer_falls_back_to_the_one_site_in_the_document():
    p = good_proposal()
    p["site"] = {"value": "Brightwell Manufacturing", "excerpt": "Cedar Mesa Power & Light", "page": 1}
    ex = extract.verify(p, PAGES, matcher)
    assert ex.site_id == "austin" and len(ex.claims) == 1 and ex.failures == []
    assert ex.site_evidence.excerpt.startswith("Service location: Austin Plant")
    assert ex.notes and "resolved by code" in ex.notes[0]


def test_no_fallback_when_the_document_names_two_sites_or_the_proposal_disagrees():
    pages = [PAGES[0] + "\nTransferred from: Reno Office"]
    p = good_proposal()
    p["site"] = {"value": "x", "excerpt": "Cedar Mesa Power & Light", "page": 1}
    ex = extract.verify(p, pages, matcher)
    assert ex.site_id is None and ex.claims == []
    p = good_proposal()
    p["site"]["value"] = "Reno Office"  # disagreement is never papered over
    ex = extract.verify(p, PAGES, matcher)
    assert ex.site_id is None and ex.claims == []
