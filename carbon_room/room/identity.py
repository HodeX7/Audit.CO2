"""Switch sender to Actor mapping and person display names."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from carbon_room import config
from carbon_room.models import Actor
from carbon_room.room.ports import AGENT_TITLES

log = logging.getLogger(__name__)

_warned_missing = False


def _people() -> list[dict] | None:
    """Return the people list, or None when people.yaml is missing."""
    global _warned_missing
    try:
        return list(config.load_people().get("people") or [])
    except FileNotFoundError:
        if not _warned_missing:
            _warned_missing = True
            log.warning("people.yaml is missing; every sender is a guest")
        return None


def _switch_ids(p: dict) -> list:
    return list(p.get("switch_ids") or [])


def actor_for(sender_id: str, sender_name: str, *,
              agent_ids: Mapping[str, str] | None = None) -> Actor:
    for p in _people() or []:
        if sender_id in _switch_ids(p):
            return Actor("human", p["id"], p["name"], p["role"])
    if agent_ids is not None and sender_id in agent_ids:
        name = agent_ids[sender_id]
        return Actor("agent", name, AGENT_TITLES[name], None)
    return Actor("human", f"guest:{sender_id}", sender_name or sender_id, None)


def person(person_id: str) -> dict | None:
    for p in _people() or []:
        if p.get("id") == person_id:
            return p
    return None


def display(person_id: str) -> str:
    p = person(person_id)
    if p is not None:
        username = str(p.get("username") or "").strip()
        if username.startswith("@"):
            username = username[1:]
        if username:
            return "@" + username
        name = str(p.get("name") or "").strip()
        if name:
            return name
    return person_id


def is_known(sender_id: str) -> bool:
    return any(sender_id in _switch_ids(p) for p in _people() or [])


def placeholders() -> list[str]:
    people = _people()
    if people is None:
        return ["people.yaml is missing"]
    problems: list[str] = []
    for p in people:
        pid = p.get("id")
        ids = _switch_ids(p)
        for value in ids:
            if "<" in str(value):
                problems.append(f"{pid}: switch_ids contains a placeholder: {value}")
        username = str(p.get("username") or "")
        if "<" in username:
            problems.append(f"{pid}: username contains a placeholder: {username}")
        if pid in ("lead", "priya") and not ids:
            problems.append(f"{pid}: switch_ids is empty")
    return problems
