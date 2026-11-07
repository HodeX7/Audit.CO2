"""Apply an authenticated gap option, then recalculate and recheck the close."""

from __future__ import annotations

from carbon_room.actors import WATCHDOG
from carbon_room.calc import run as calc_run
from carbon_room.checks import run as check_run
from carbon_room.ledger import ledger
from carbon_room.models import NeedsRoomEvent, NotAllowed, NotFound


def _open_gap(conn, gap_id):
    close_id = ledger.latest_close(conn)
    if close_id is None:
        raise NotFound(f"no open gap {gap_id}")
    row = conn.execute(
        "SELECT 1 FROM gaps WHERE close_id=? AND gap_id=? AND status='OPEN'", (close_id, gap_id)
    ).fetchone()
    if row is None:
        raise NotFound(f"no open gap {gap_id} on latest close {close_id}")
    return close_id, ledger.get_gap(conn, gap_id, close_id)


def apply(conn, gap_id, action, actor, chat_message_id, payload):
    """Treat the option and P3-authenticated actor/message as the only authority for a human action."""
    if actor.kind != "human":
        raise NotAllowed("gap resolution requires an authenticated human")
    if not chat_message_id:
        raise NeedsRoomEvent("human resolutions require a Switch chat_message_id")
    if not isinstance(payload, dict):
        raise ValueError("resolution payload must be a mapping")
    close_id, gap = _open_gap(conn, gap_id)
    if ledger.get_close(conn, close_id)["phase"] == "PUBLISHED":
        raise NotAllowed("published close cannot be resolved; start a new version")
    options = [option for option in gap.options if option.action == action]
    if not options:
        raise ValueError(f"{action!r} is not an option for {gap_id}")
    if action == "pick" and not any(option.params.get("claim_id") == payload.get("claim_id") for option in options):
        raise ValueError(f"selected claim is not an option for {gap_id}")
    from carbon_room import config

    allowed = config.load_config()["approvals"]["approve_roles"]
    if actor.id != gap.owner and actor.role not in allowed:
        raise NotAllowed(f"{gap_id} may be resolved by {gap.owner} or a role in {allowed}")
    reason = str(payload.get("reason") or f"{action} in {gap_id}")
    if action == "upload":
        from carbon_room import collect

        path = payload.get("path")
        if not path:
            raise ValueError("upload requires payload['path']")
        expected = next(option.params for option in options if option.action == "upload")
        new_claims = collect.ingest_file(
            conn,
            close_id,
            path,
            actor,
            site=expected["site"],
            month_from_period=True,
            chat_message_id=chat_message_id,
            expected=(expected["site"], expected["month"], expected["activity"]),
        )
        valid = [
            claim_id
            for claim_id in new_claims
            if (
                (claim := ledger.get_claim(conn, claim_id)).site == expected["site"]
                and claim.month == expected["month"]
                and claim.activity == expected["activity"]
            )
        ]
        if not valid:
            raise ValueError("uploaded evidence has no matching current-period claim; gap stays open")
        for old in gap.claim_ids:
            ledger.supersede(conn, old, valid[0], actor, f"replaced by upload in {gap_id}", chat_message_id)
        ledger.resolve_gap(
            conn, close_id, gap_id, actor, chat_message_id, {"outcome": "uploaded", "claim_id": valid[0]}
        )
    elif action == "pick":
        chosen = payload["claim_id"]
        for loser in gap.claim_ids:
            if loser != chosen:
                ledger.supersede(conn, loser, chosen, actor, f"human picked {chosen} in {gap_id}", chat_message_id)
        ledger.add_approval(conn, close_id, "claim", chosen, 2, actor, "approve", reason, chat_message_id)
        ledger.resolve_gap(conn, close_id, gap_id, actor, chat_message_id, {"outcome": "picked", "claim_id": chosen})
    elif action == "approve":
        use_factor_id = payload.get("use_factor_id")
        required_factors = {option.params["use_factor_id"] for option in options if "use_factor_id" in option.params}
        if required_factors and use_factor_id not in required_factors:
            raise ValueError("this approval must select the locked factor option")
        if use_factor_id and not any(option.params.get("use_factor_id") == use_factor_id for option in options):
            raise ValueError("factor is not an approved option for this gap")
        for claim_id in gap.claim_ids:
            if use_factor_id:
                factor = ledger.get_factor(conn, use_factor_id)
                ledger.set_factor(conn, claim_id, use_factor_id, factor["version"], actor, reason, chat_message_id)
            ledger.add_approval(conn, close_id, "claim", claim_id, 2, actor, "approve", reason, chat_message_id)
        ledger.resolve_gap(conn, close_id, gap_id, actor, chat_message_id, {"outcome": "approved"})
    elif action == "reject":
        for claim_id in gap.claim_ids:
            ledger.add_approval(conn, close_id, "claim", claim_id, 2, actor, "reject", reason, chat_message_id)
        ledger.resolve_gap(conn, close_id, gap_id, actor, chat_message_id, {"outcome": "excluded", "reason": reason})
    else:
        raise ValueError(f"unsupported action {action!r}")
    ledger.set_phase(conn, close_id, "RECHECKING", WATCHDOG)
    calc_run.calculate(conn, close_id)
    return check_run.check(conn, close_id)
