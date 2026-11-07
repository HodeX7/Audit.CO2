"""Stable source-tag selection for every verified calculation and basis."""

from carbon_room.ledger import ledger


def assign(conn, close_id: str, version: int, month: str) -> list[str]:
    claims = sorted(
        (claim for claim in ledger.get_claims(conn, close_id, month=month) if claim.status == "VERIFIED"),
        key=lambda claim: (claim.site, claim.activity, claim.claim_id),
    )
    calculations = [calc for claim in claims for calc in ledger.live_calculations(conn, claim.claim_id)]
    ids = [calc.calc_id for calc in calculations if calc is not None]
    assigned = ledger.assign_s_tags(conn, close_id, version, ids)
    return [assigned[calc_id] for calc_id in ids]
