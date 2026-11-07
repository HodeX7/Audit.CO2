"""Shared, close-scoped inputs and stable identities for deterministic Watchdog rules."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from carbon_room import config
from carbon_room.ledger import ledger
from carbon_room.models import Finding


def owner_for(site_id: str) -> str:
    """Resolve ownership from the active configuration, not seed literals."""
    return config.site_owner(site_id)


@dataclass
class CheckContext:
    conn: object
    close: dict
    claims: list
    sources: list
    gaps: list
    approvals: list[dict]
    settings: dict

    @classmethod
    def load(cls, conn, close_id: str) -> CheckContext:
        return cls(
            conn,
            ledger.get_close(conn, close_id),
            ledger.get_claims(conn, close_id),
            ledger.get_sources(conn, close_id),
            ledger.get_gaps(conn, close_id),
            ledger.get_approvals(conn, close_id),
            config.load_config(),
        )

    @property
    def current(self) -> list:
        return [claim for claim in self.claims if claim.month == self.close["month"]]

    def calc(self, claim, basis=None):
        if basis is None:
            return ledger.latest_calculation(self.conn, claim.claim_id)
        return ledger.latest_calculation(self.conn, claim.claim_id, basis)

    def owner(self, site: str) -> str:
        return owner_for(site)

    @property
    def lead(self) -> str:
        return self.settings["approvals"]["default_owner"]


def make_finding(rule, kind, claim_ids, site, month, owner, title, evidence, options, tier, blocking) -> Finding:
    claim_ids = sorted(claim_ids)
    key = "|".join((rule, kind, site, month, ",".join(claim_ids)))
    finding_id = "F-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
    return Finding(finding_id, rule, kind, claim_ids, site, month, owner, title, evidence, options, tier, blocking)
