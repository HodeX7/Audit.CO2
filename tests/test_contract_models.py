from decimal import Decimal

from carbon_room.models import Claim, from_dict, to_dict


def test_claim_round_trip_preserves_decimal_precision():
    claim = Claim(
        claim_id="CL-0012", close_id="2026-10-v1", site="hq", month="2026-10", activity="electricity_kwh",
        value=Decimal("48200.0"), unit="kWh", scope="2", source_doc_id="SRC-0001", source_excerpt="48,200 kWh",
        source_sha256="a" * 64, source_page=1, factor_id=None, factor_version=None, status="UNVERIFIED",
        extracted_by="collector", checked_by=None, superseded_by=None,
    )
    restored = from_dict(Claim, to_dict(claim))
    assert restored == claim
    assert restored.value == Decimal("48200.0")
