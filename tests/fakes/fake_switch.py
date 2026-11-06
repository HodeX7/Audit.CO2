"""In-process fake Switch WebSocket server for connection tests (SPEC-07)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

_QUIET = logging.getLogger("fake_switch.wire")
_QUIET.setLevel(logging.WARNING)
_PATH = re.compile(r"/agents/([^/]+)/connection/ws")


@dataclass
class Record:
    agent_id: str
    query: dict[str, str]
    auth: str | None
    pongs: list[tuple[float, int]]
    pings_sent: list[float]
    closed: bool = False


class FakeSwitch:
    def __init__(
        self,
        *,
        ping_interval: float = 2.0,
        evict_after: float = 6.0,
        control_style: Literal["type", "event"] = "type",
        api_keys: dict[str, str] | None = None,
    ) -> None:
        self.ping_interval = ping_interval
        self.evict_after = evict_after
        self.control_style = control_style
        self.api_keys = api_keys
        self.connections: list[Record] = []
        self.next_sequence = 1
        self.buffers: dict[str, list[dict]] = {}
        self._server = None
        self._sockets: dict[str, object] = {}
        self._all: set[object] = set()
        self._opens: dict[str, int] = {}
        self._refuse: dict[str, int] = {}
        self._ready: set[int] = set()

    async def start(self) -> str:
        self._server = await serve(self._handler, "127.0.0.1", 0, logger=_QUIET)
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        for ws in list(self._all):
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 - best effort teardown
                pass
        server.close()
        await server.wait_closed()

    # ---- frames -------------------------------------------------------------------------------
    def _control(self, kind: str, fields: dict) -> str:
        if self.control_style == "event":
            return json.dumps({"event": kind, "data": dict(fields)})
        return json.dumps({"type": kind, **fields})

    @staticmethod
    async def _send(ws, text: str) -> None:
        try:
            await ws.send(text)
        except ConnectionClosed:
            pass

    async def _handler(self, ws) -> None:
        parsed = urlsplit(ws.request.path)
        match = _PATH.fullmatch(parsed.path)
        if not match:
            await ws.close(4400)
            return
        agent_id = match.group(1)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        auth = ws.request.headers.get("Authorization")
        rec = Record(agent_id, query, auth, [], [])
        self.connections.append(rec)
        self._all.add(ws)
        heartbeat: asyncio.Task | None = None
        try:
            token = auth[len("Bearer "):] if auth and auth.startswith("Bearer ") else ""
            if not token:
                await ws.close(4401)
                return
            if self.api_keys is not None and self.api_keys.get(agent_id) != token:
                await ws.close(4401)
                return
            refusal = self._refuse.pop(agent_id, None)
            if refusal is not None:
                await ws.close(refusal)
                return
            opens = self._opens.get(agent_id, 0) + 1
            self._opens[agent_id] = opens
            start_from = int(query["start_from"]) if "start_from" in query else None
            await self._send(
                ws,
                self._control(
                    "connection_state",
                    {
                        "generation": opens,
                        "cursor": start_from if start_from is not None else self.next_sequence - 1,
                        "connection_id": query.get("connection_id"),
                        "agent_id": agent_id,
                        "rooms": [r for r in query.get("rooms", "").split(",") if r],
                        "filter": query.get("filter"),
                        "heartbeat_interval_seconds": self.ping_interval,
                    },
                ),
            )
            self._ready.add(id(rec))
            last_sent = start_from
            while last_sent is not None:
                pending = [f for f in self.buffers.get(agent_id, []) if f["id"] > last_sent]
                if not pending:
                    break
                for frame in pending:
                    await self._send(ws, json.dumps(frame))
                    last_sent = frame["id"]
            self._sockets[agent_id] = ws
            last_pong = [time.monotonic()]
            heartbeat = asyncio.create_task(self._heartbeat(ws, rec, last_pong))
            try:
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "pong" and isinstance(msg.get("cursor"), int):
                        now = time.monotonic()
                        last_pong[0] = now
                        rec.pongs.append((now, msg["cursor"]))
            except ConnectionClosed:
                pass
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
            rec.closed = True
            self._all.discard(ws)
            if self._sockets.get(agent_id) is ws:
                del self._sockets[agent_id]

    async def _heartbeat(self, ws, rec: Record, last_pong: list[float]) -> None:
        while True:
            await asyncio.sleep(self.ping_interval)
            rec.pings_sent.append(time.monotonic())
            await self._send(ws, self._control("ping", {}))
            if time.monotonic() - last_pong[0] >= self.evict_after:
                await self._send(ws, self._control("evicted", {"code": "heartbeat_lapsed", "reason": "no pong"}))
                try:
                    await ws.close(1000)
                except ConnectionClosed:
                    pass
                return

    # ---- test controls ------------------------------------------------------------------------
    async def inject(self, agent_id: str, payload: dict, *, room_id: str = "room-1", kind: str = "message") -> int:
        seq = self.next_sequence
        self.next_sequence += 1
        frame = {
            "event": kind,
            "data": {
                "type": kind,
                "room_id": room_id,
                "bridge_id": None,
                "channel_type": "channel_public",
                "payload": payload,
                "sequence": seq,
            },
            "id": seq,
        }
        self.buffers.setdefault(agent_id, []).append(frame)
        ws = self._sockets.get(agent_id)
        if ws is not None:
            await self._send(ws, json.dumps(frame))
        return seq

    async def drop(self, agent_id: str, code: int = 1012) -> None:
        ws = self._sockets.pop(agent_id, None)
        if ws is not None:
            await ws.close(code)

    async def evict(self, agent_id: str, code: str = "heartbeat_lapsed") -> None:
        ws = self._sockets.pop(agent_id, None)
        if ws is not None:
            await self._send(ws, self._control("evicted", {"code": code, "reason": "test"}))
            await ws.close(1000)

    async def send_raw(self, agent_id: str, frame: dict) -> None:
        ws = self._sockets.get(agent_id)
        if ws is not None:
            await self._send(ws, json.dumps(frame))

    def refuse_next(self, agent_id: str, code: int) -> None:
        self._refuse[agent_id] = code

    async def wait_for_connections(self, agent_id: str, n: int, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            recs = [r for r in self.connections if r.agent_id == agent_id]
            if len(recs) >= n and id(recs[-1]) in self._ready:
                return
            await asyncio.sleep(0.01)
        raise TimeoutError(f"{agent_id}: {n} connections not reached")

    @staticmethod
    def message(
        *,
        body: str,
        message_id: str,
        sender: str = "@switch-user-lead:test",
        sender_name: str = "lead",
        addressed: bool = True,
        thread_id: str | None = None,
        attachments: list[dict] | None = None,
        timestamp: int = 1793000000000,
    ) -> dict:
        return {
            "addressed": addressed,
            "sender": sender,
            "sender_name": sender_name,
            "message_id": message_id,
            "body": body,
            "timestamp": timestamp,
            "thread_id": thread_id,
            "attachments": attachments or [],
        }
