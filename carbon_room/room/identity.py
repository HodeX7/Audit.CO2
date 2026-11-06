"""Switch sender to Actor mapping and person display names."""

from __future__ import annotations

from collections.abc import Mapping

from carbon_room.models import Actor


def actor_for(sender_id: str, sender_name: str, *,
              agent_ids: Mapping[str, str] | None = None) -> Actor:
    raise NotImplementedError


def person(person_id: str) -> dict | None:
    raise NotImplementedError


def display(person_id: str) -> str:
    raise NotImplementedError


def is_known(sender_id: str) -> bool:
    raise NotImplementedError


def placeholders() -> list[str]:
    raise NotImplementedError
