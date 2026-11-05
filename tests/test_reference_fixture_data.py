"""Regression coverage for the sourced, synthetic P1 data corpus."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from carbon_room import collect
from carbon_room.ledger import ledger
from carbon_room.models import Actor
from carbon_room.sources.readers import read


FIXTURES = Path("tests/fixtures/emissions_reference")
SYSTEM = Actor("system", "collector", "Collector")


def _cases() -> list[dict]:
    return json.loads((FIXTURES / "pinned_reference_cases.json").read_text(encoding="utf-8"))["cases"]


def test_reference_fixture_metadata_is_pinned_synthetic_and_arithmetically_reviewable():
    payload = json.loads((FIXTURES / "pinned_reference_cases.json").read_text(encoding="utf-8"))
    assert payload["test_only"] is True
    assert "production factor loading" in payload["excluded"]

    for case in payload["cases"]:
        expected = case["expected_test_only"]
        assert (FIXTURES / case["document"]).is_file()
        assert case["provenance"]["url"].startswith("https://")
        assert case["provenance"]["edition"]
        if "factor_kgco2e_per_unit" in expected:
            assert Decimal(case["quantity"]) * Decimal(expected["factor_kgco2e_per_unit"]) == Decimal(expected["kgco2e"])
        else:
            assert expected["does_not_calculate_kgco2e"] is True


def test_reference_fixture_documents_are_readable_and_match_declared_kind():
    for case in _cases():
        kind, pages = read(FIXTURES / case["document"])
        assert kind == case["kind"]
        assert isinstance(pages, list)
        assert "SYNTHETIC" in "\n".join(pages)


def test_reference_fixture_documents_ingest_as_unverified_p1_evidence(db, tmp_path, monkeypatch):
    close_id = ledger.create_close(
        db, "2026-10", ["warehouse-2", "dc-eu-west"], "FS-test", SYSTEM, "switch-close",
    )
    db.commit()
    real_store_file = collect.store_file
    monkeypatch.setattr(
        collect,
        "store_file",
        lambda path: real_store_file(path, tmp_path / "content-addressed-store"),
    )

    ingested: dict[str, object] = {}
    for case in _cases():
        claim_ids = collect.ingest_file(
            db, close_id, FIXTURES / case["document"], SYSTEM, site=case["site"], month_from_period=True,
        )
        assert len(claim_ids) == 1
        ingested[case["id"]] = ledger.get_claim(db, claim_ids[0])

    for case in _cases():
        claim = ingested[case["id"]]
        assert claim.activity == case["activity"]
        assert claim.value == Decimal(case["quantity"])
        assert claim.unit == case["unit"]
        assert claim.month == case["period_start"][:7]
        assert claim.status == "UNVERIFIED"

    sources = ledger.get_sources(db, close_id)
    assert len(sources) == len(_cases())
    assert all(source.extract_status == "OK" for source in sources)
    assert all("SYNTHETIC" in source.raw_text for source in sources)
    by_file_name = {source.file_name: source for source in sources}
    for case in _cases():
        source = by_file_name[case["document"]]
        assert source.period_start == case["period_start"]
        assert source.period_end == case["period_end"]
    cloud_claim = ingested["p1-cloud-provider-envelope-2024"]
    assert cloud_claim.attributes == {
        "accounting_method": "provider-allocated",
        "methodology_version": "synthetic-envelope-v1",
        "provider": "fictional-cloud",
        "pue": "1.20",
        "region": "eu-west-1",
        "vendor_factor_ref": "test-only provenance in pinned_reference_cases.json",
        "ai_breakdown_available": False,
    }
