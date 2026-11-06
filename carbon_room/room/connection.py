"""One Switch WebSocket per agent.

The read loop answers every ping inline, tracks the highest sequence seen, hands domain frames to a
synchronous callback, and reconnects with backoff, resuming from its cursor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from typing import Any, Literal
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from carbon_room.room import frames

log = logging.getLogger(__name__)
WIRE_LOG = logging.getLogger("carbon_room.room.connection.wire")
WIRE_LOG.setLevel(logging.WARNING)

_FINAL_EVICTIONS = frozenset({"taken_over", "closed"})
_FINAL_CLOSE_CODES = frozenset({4400, 4403, 4409})
_RECONNECT = "reconnect"
_FINAL = "final"


class AuthError(Exception):
    """Switch rejected the agent's API key."""


def backoff_delays() -> Iterator[float]:
    for delay in (1, 2, 4, 8, 16):
        yield delay
    while True:
        yield 30


class AgentConnection:
    def __init__(
        self,
        agent_name: str,
        agent_id: str,
        api_key: str,
        server: str,
        room_ids: list[str],
        filter: Literal["all", "addressed"],
        on_event: Callable[[str, dict], None],
        *,
        connection_id: str | None = None,
        client_version: str = "0.1.0",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.agent_name = agent_name
        self.agent_id = agent_id
        self._api_key = api_key
        self.server = server
        self.room_ids = list(room_ids)
        self.filter = filter
        self.on_event = on_event
        self.connection_id = connection_id or str(uuid.uuid4())
        self.client_version = client_version
        self._sleep = sleep
        self.cursor: int | None = None
        self.generation: int | None = None
        self.connected = asyncio.Event()
        self._stopping = False
        self._stop_event = asyncio.Event()
        self._ws: Any = None
        self._backoff = backoff_delays()

    # ---- public -------------------------------------------------------------------------------
    def url(self) -> str:
        base = self.server.rstrip("/")
        if base.startswith("https://"):
            base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://"):]
        query = [
            ("connection_id", self.connection_id),
            ("rooms", ",".join(self.room_ids)),
            ("filter", self.filter),
            ("client", "carbon-room-python"),
            ("client_version", self.client_version),
        ]
        if self.cursor is not None:
            query.append(("start_from", self.cursor))
        if self.generation is not None:
            query.append(("expected_generation", self.generation))
        return f"{base}/agents/{self.agent_id}/connection/ws?{urlencode(query)}"

    async def run(self) -> None:
        stopper = asyncio.ensure_future(self._stop_event.wait())
        try:
            while not self._stopping:
                done, result = await self._race(self._attempt(), stopper)
                if not done or self._stopping:
                    return
                if result == _FINAL:
                    return
                self.connected.clear()
                delay = next(self._backoff)
                done, _ = await self._race(self._sleep(delay), stopper)
                if not done:
                    return
        finally:
            stopper.cancel()
            self.connected.clear()

    async def stop(self) -> None:
        self._stopping = True
        self._stop_event.set()
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 - already closing
                log.debug("close during stop failed for %s", self.agent_name, exc_info=True)

    def __repr__(self) -> str:
        return f"AgentConnection({self.agent_name!r}, rooms={self.room_ids!r}, filter={self.filter!r})"

    # ---- internals ----------------------------------------------------------------------------
    @staticmethod
    async def _race(coro: Coroutine[Any, Any, Any], stopper: asyncio.Future) -> tuple[bool, Any]:
        """Run coro until it finishes or stopper does. Returns (finished, result)."""
        task = asyncio.ensure_future(coro)
        try:
            await asyncio.wait({task, stopper}, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            task.cancel()
            raise
        if task.done():
            return True, task.result()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - discarding a cancelled attempt
            pass
        return False, None

    async def _attempt(self) -> str:
        """One connection attempt. Returns _RECONNECT or _FINAL; raises AuthError."""
        try:
            async with connect(
                self.url(),
                additional_headers={"Authorization": f"Bearer {self._api_key}"},
                ping_interval=None,
                logger=WIRE_LOG,
            ) as ws:
                self._ws = ws
                try:
                    return await self._serve(ws)
                finally:
                    self._ws = None
        except ConnectionClosed as exc:
            return self._on_closed(exc)
        except InvalidStatus as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise AuthError(f"Switch rejected the key for {self.agent_name}") from None
            log.warning("handshake for %s failed with HTTP %s", self.agent_name, status)
            return _RECONNECT
        except (OSError, TimeoutError, InvalidHandshake) as exc:
            log.warning("connection for %s failed: %s", self.agent_name, exc)
            return _RECONNECT

    def _on_closed(self, exc: ConnectionClosed) -> str:
        if self._stopping:
            return _FINAL
        code = exc.rcvd.code if exc.rcvd is not None else None
        if code == 4401:
            raise AuthError(f"Switch rejected the key for {self.agent_name}") from None
        if code in _FINAL_CLOSE_CODES:
            log.error("Switch closed the connection for %s with code %s; not retrying", self.agent_name, code)
            return _FINAL
        log.warning("connection for %s closed (code %s); reconnecting", self.agent_name, code)
        return _RECONNECT

    @staticmethod
    def _parse(raw: str | bytes) -> dict | None:
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            log.warning("skipping a frame that is not valid JSON")
            return None
        if not isinstance(frame, dict):
            log.warning("skipping a frame that is not an object")
            return None
        return frame

    async def _serve(self, ws: Any) -> str:
        first = self._parse(await ws.recv())
        if first is None or frames.frame_kind(first) != "connection_state":
            log.warning("first frame for %s was not connection_state; reconnecting", self.agent_name)
            await ws.close()
            return _RECONNECT
        self._on_state(first)
        log.info(
            "connected agent=%s rooms=%s filter=%s", self.agent_name, ",".join(self.room_ids), self.filter
        )
        self._backoff = backoff_delays()
        self.connected.set()
        async for raw in ws:
            frame = self._parse(raw)
            if frame is None:
                continue
            outcome = await self._handle(ws, frame)
            if outcome is not None:
                return outcome
        return _RECONNECT

    def _on_state(self, frame: dict) -> None:
        fields = frames.frame_fields(frame)
        generation = fields.get("generation")
        if isinstance(generation, int) and not isinstance(generation, bool):
            self.generation = generation
        cursor = fields.get("cursor")
        if self.cursor is None and isinstance(cursor, int) and not isinstance(cursor, bool):
            self.cursor = cursor

    async def _handle(self, ws: Any, frame: dict) -> str | None:
        kind = frames.frame_kind(frame)
        if kind == "ping":
            await ws.send(frames.pong(self.cursor or 0))
        elif kind in frames.DOMAIN_KINDS:
            self._domain(frame)
        elif kind == "gap":
            resumed_at = frames.frame_fields(frame).get("resumed_at")
            if isinstance(resumed_at, int) and not isinstance(resumed_at, bool):
                self.cursor = resumed_at - 1
                log.info("gap for %s: resuming at %s", self.agent_name, resumed_at)
        elif kind == "refused":
            fields = frames.frame_fields(frame)
            log.warning(
                "Switch refused for %s: status=%s detail=%s",
                self.agent_name,
                fields.get("status"),
                fields.get("detail"),
            )
        elif kind == "evicted":
            fields = frames.frame_fields(frame)
            code = fields.get("code")
            log.warning("evicted %s: code=%s reason=%s", self.agent_name, code, fields.get("reason"))
            await ws.close()
            return _FINAL if code in _FINAL_EVICTIONS else _RECONNECT
        elif kind == "connection_state":
            self._on_state(frame)
            log.info("connection_state update for %s: generation=%s", self.agent_name, self.generation)
        elif kind in ("subscription_changed", "room_released"):
            log.info("%s for %s", kind, self.agent_name)
        else:
            log.debug("ignoring frame of kind %r for %s", kind, self.agent_name)
        return None

    def _domain(self, frame: dict) -> None:
        seq = frames.sequence_of(frame)
        if seq is not None and self.cursor is not None and seq <= self.cursor:
            log.debug("skipping duplicate sequence %s for %s", seq, self.agent_name)
            return
        if seq is not None:
            self.cursor = seq
        try:
            self.on_event(self.agent_name, frame)
        except Exception:
            log.exception("on_event failed for %s", self.agent_name)
