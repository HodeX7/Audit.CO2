"""Decode raw Switch frames into RoomEvent."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from carbon_room.room import frames
from carbon_room.room.ports import AGENT_NAMES

log = logging.getLogger(__name__)


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
        return self.thread_id is not None and self.thread_id != self.message_id


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str_or_empty(value: object) -> str | None:
    if value is None:
        return ""
    return value if isinstance(value, str) else None


def _attachment(raw: dict) -> Attachment:
    filename = raw.get("filename")
    return Attachment(
        filename=filename if isinstance(filename, str) else "",
        mimetype=raw.get("mimetype"),
        size=_int(raw.get("size")),
        mxc=raw.get("mxc"),
        msgtype=raw.get("msgtype"),
    )


def _is_own(sender: str, sender_name: str, own_sender_ids: frozenset[str]) -> bool:
    return sender in own_sender_ids or sender_name.strip().lower() in AGENT_NAMES


def _decode(frame: dict, receiving_agent: str, own_sender_ids: frozenset[str]) -> RoomEvent | None:
    kind = frames.frame_kind(frame)
    if kind not in ("message", "room_join"):
        return None
    fields = frames.frame_fields(frame)
    payload = fields.get("payload")
    room_id = fields.get("room_id")
    sequence = frames.sequence_of(frame)
    if not isinstance(payload, dict) or not isinstance(room_id, str) or not room_id:
        return None
    if sequence is None:
        return None

    timestamp = _int(payload.get("timestamp")) or 0
    if kind == "room_join":
        sender = payload.get("member") or ""
        sender_name = payload.get("member_name") or ""
        if not isinstance(sender, str) or not isinstance(sender_name, str):
            return None
        if _is_own(sender, sender_name, own_sender_ids):
            return None
        return RoomEvent("room_join", room_id, f"join:{sequence}", None, sender, sender_name, "",
                         (), False, timestamp, receiving_agent, sequence)

    message_id = payload.get("message_id")
    if not isinstance(message_id, str) or not message_id:
        return None
    sender = _str_or_empty(payload.get("sender"))
    sender_name = _str_or_empty(payload.get("sender_name"))
    body = _str_or_empty(payload.get("body"))
    if sender is None or sender_name is None or body is None:
        return None
    thread_id = payload.get("thread_id")
    if thread_id is not None and not isinstance(thread_id, str):
        return None
    thread_id = thread_id or None
    if _is_own(sender, sender_name, own_sender_ids):
        return None
    raw_attachments = payload.get("attachments")
    attachments = tuple(
        _attachment(a) for a in (raw_attachments if isinstance(raw_attachments, list) else [])
        if isinstance(a, dict)
    )
    return RoomEvent("message", room_id, message_id, thread_id, sender, sender_name, body,
                     attachments, payload.get("addressed") is True, timestamp,
                     receiving_agent, sequence)


def decode(
    frame: dict, receiving_agent: str, own_sender_ids: frozenset[str] = frozenset()
) -> RoomEvent | None:
    try:
        return _decode(frame, receiving_agent, own_sender_ids)
    except Exception:
        log.debug("could not decode frame", exc_info=True)
        return None
