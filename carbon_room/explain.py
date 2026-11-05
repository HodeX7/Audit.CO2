"""Map questions to ledger facts before asking the model to phrase them."""

from __future__ import annotations

from carbon_room import config, llm
from carbon_room.ledger import ledger


def answer(conn, close_id: str, question: str, actor) -> str:
    """Use only matching VERIFIED claims; otherwise give the responsible owner."""
    query = question.lower()
    site_id = next((item["id"] for item in config.load_sites()["sites"] if item["id"] in query or item["name"].lower() in query), None)
    activity = "diesel_l" if "diesel" in query else "electricity_kwh" if "electric" in query else "dc_it_kwh" if "cloud" in query else None
    claims = ledger.get_claims(conn, close_id, site=site_id, activity=activity)
    verified = [claim for claim in claims if claim.status == "VERIFIED"]
    if not verified:
        owner = config.site_owner(site_id) if site_id else "lead"
        gaps = ledger.get_gaps(conn, close_id, status="OPEN")
        owner = next((gap.owner for gap in gaps if not site_id or any(claim.site == site_id for claim in claims)), owner)
        return llm.phrase(question, [], "carbon-room", close_id, scope=site_id or "this close", owner=owner)
    facts = []
    for claim in verified:
        calculation = ledger.latest_calculation(conn, claim.claim_id)
        emissions = f", {calculation.kgco2e} kgCO2e" if calculation else ", no calculation recorded"
        facts.append(f"{claim.claim_id}: {claim.site} {claim.value} {claim.unit}{emissions}, status {claim.status}")
    return llm.phrase(question, facts, "carbon-room", close_id)
