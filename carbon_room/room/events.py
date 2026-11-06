"""Decode raw Switch frames into RoomEvent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Attachment:
    filename: str
    mimetype: str | None
    size: int | None
    mxc: str | None
    msgtype: str | None


@dataclass(frozen=True)
class RoomEvent:
    type: str
    room_id: str
    message_id: str
    thread_id: str | None
    sender: str
    sender_name: str
    body: str
    attachments: tuple[Attachment, ...]
    addressed: bool
    timestamp: int
    receiving_agent: str
    sequence: int

    @property
    def in_thread(self) -> bool:
        raise NotImplementedError


def decode(
    frame: dict, receiving_agent: str, own_sender_ids: frozenset[str] = frozenset()
) -> RoomEvent | None:
    raise NotImplementedError
