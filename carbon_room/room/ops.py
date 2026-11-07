# ops.py – Switch operations client for SPEC‑08
# This file implements the OpsClient described in docs/p3/specs/SPEC-08-ops.md.
# All constants are derived from docs/switch-ops.json and are kept in sync with the spec.

import json
import logging
from typing import Any, Mapping, Sequence
import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants – §0 (filled from SPEC‑08)
# ---------------------------------------------------------------------------
POST_TEXT_ARG = "body"
POST_ROOM_ARG = None  # room is implicit per Switch docs
POST_THREAD_ARG = "thread_id"
POST_ID_KEY = "event_id"
TARGETED_TO_ARG = "target_names"
TARGETED_TO_KIND = "names"
TARGETED_TEXT_ARG = "body"
READ_LIMIT_ARG = "limit"
READ_THREADS_KEY = "threads"
CONTEXT_ID_KEY = "id"
CONTEXT_BODY_KEY = "body"
CONTEXT_SENDER_KEY = "sender"
CONTEXT_TIME_KEY = "timestamp"
CONTEXT_KIND_KEY = "kind"
DOCS_SUPPORTED = True
DOC_NAME_ARG = "name"
DOC_CONTENT_ARG = "content"
DOC_CREATE_EXTRA = {
    "description": "Live close figures and open gaps.",
    "instructions": "Status board kept up to date by carbon-room. Read it; don't edit it.",
}
DOC_ID_ARG = "document_id"
DOC_ID_KEY = "document_id"
CONNECT_BEFORE_ROOM_OPS = True

# Op name constants
POST_MESSAGE = "post_message"
SEND_TARGETED = "send_targeted_message"
READ_CONTEXT = "read_context"
CREATE_DOC = "create_room_document"
UPDATE_DOC = "update_room_document"
CONNECT_ROOM = "connect_to_room"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class SwitchError(Exception):
    """Raised for any Switch‑API error.

    Attributes
    ----------
    status: int | None – HTTP status code (or ``None`` for transport errors)
    op: str – the operation that failed
    detail: str – human‑readable error message
    """

    def __init__(self, status: int | None, op: str, detail: str) -> None:
        self.status = status
        self.op = op
        self.detail = detail
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.status is None:
            return f"{self.op} failed: {self.detail}"
        return f"{self.op} failed ({self.status}): {self.detail}"

# ---------------------------------------------------------------------------
# OpsClient implementation
# ---------------------------------------------------------------------------
class OpsClient:
    """Async wrapper for Switch operations.

    Parameters
    ----------
    server: str – base URL for the Switch server (no trailing slash).
    agent_id: str – the Switch agent ID this client represents.
    api_key: str – bearer token for authentication.
    connection_id: str | None – optional connection identifier.
    room_id: str | None – optional room identifier for room‑scoped ops.
    transport: httpx.AsyncBaseTransport | None – custom transport (e.g. MockTransport in tests).
    timeout: float – request timeout in seconds.
    agent_ids: Mapping[str, str] | None – mapping of agent name → Switch ID for targeted messages.
    """

    def __init__(
        self,
        server: str,
        agent_id: str,
        api_key: str,
        *,
        connection_id: str | None = None,
        room_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        agent_ids: Mapping[str, str] | None = None,
    ) -> None:
        self.server = server.rstrip('/')
        self.agent_id = agent_id
        self.api_key = api_key
        self.connection_id = connection_id
        self.room_id = room_id
        self.agent_ids = agent_ids
        self._client = httpx.AsyncClient(base_url=self.server, transport=transport, timeout=timeout)
        self._ops_cache: dict[str, dict] | None = None
        self._doc_id_cache: dict[str, str] = {}

    # ---------------------------------------------------------------------
    # Low‑level helpers
    # ---------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        url = f"/agents/{self.agent_id}/ops/{path}" if not path.startswith('/') else path
        hdrs = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.connection_id is not None:
            hdrs["X-Switch-Connection-Id"] = self.connection_id
        if headers:
            hdrs.update(headers)
        try:
            resp = await self._client.request(method, url, json=json or {}, headers=hdrs)
        except httpx.TransportError as exc:  # pragma: no cover – exercised via tests
            raise SwitchError(None, path, str(exc) or type(exc).__name__)
        if resp.status_code >= 400:
            # Try to extract a detail field from JSON, otherwise fall back to text
            try:
                body = resp.json()
                detail = body.get("detail")
                if detail is None:
                    detail = json.dumps(body)
                elif not isinstance(detail, str):
                    detail = json.dumps(detail)
            except Exception:
                detail = resp.text[:300]
            raise SwitchError(resp.status_code, path, detail)
        return resp

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    async def list_ops(self) -> dict[str, dict]:
        """Return a mapping ``{op_name: op_description}``.

        The result is cached after the first successful request.
        """
        if self._ops_cache is not None:
            return self._ops_cache
        resp = await self._request("GET", "")
        data = resp.json()
        self._ops_cache = data.get("operations", {})
        return self._ops_cache

    async def call(self, op: str, args: dict | None = None) -> Any:
        """Invoke a Switch operation.

        ``args`` is sent as the JSON body. The unwrapped ``result`` field is returned.
        If the response lacks ``result`` a :class:`SwitchError` is raised.
        """
        resp = await self._request("POST", op, json=args or {})
        payload = resp.json()
        if "result" not in payload:
            raise SwitchError(resp.status_code, op, "response has no result")
        return payload["result"]

    async def connect_room(self) -> dict:
        """Connect the client session to ``self.room_id``.

        Raises ``SwitchError`` if ``room_id`` or ``connection_id`` is missing.
        The result is cached to avoid duplicate calls.
        """
        if self.room_id is None or self.connection_id is None:
            raise SwitchError(None, CONNECT_ROOM, "no room or connection id")
        if hasattr(self, "_connect_cache") and self._connect_cache is not None:
            return self._connect_cache
        result = await self.call(CONNECT_ROOM, {"room_id": self.room_id, "include_general_instructions": False})
        if warning := result.get("warning"):
            log.warning("connect_to_room: %s", warning)
        self._connect_cache = result
        return result

    async def _ensure_connected(self) -> None:
        if CONNECT_BEFORE_ROOM_OPS:
            await self.connect_room()

    async def post(self, text: str, thread_id: str | None = None) -> str:
        """Post a message (optionally to a thread) and return its ID.

        The implementation follows the contract in SPEC‑08.
        """
        await self._ensure_connected()
        args: dict[str, Any] = {POST_TEXT_ARG: text}
        if POST_ROOM_ARG and self.room_id:
            args[POST_ROOM_ARG] = self.room_id
        if thread_id:
            if POST_THREAD_ARG is None:
                raise SwitchError(None, POST_MESSAGE, "threads unsupported")
            args[POST_THREAD_ARG] = thread_id
        result = await self.call(POST_MESSAGE, args)
        if POST_ID_KEY and isinstance(result, dict):
            mid = result.get(POST_ID_KEY)
            if mid is not None:
                return str(mid)
        # Fallback: read recent context and locate the message by body
        msgs = await self.read_context(10)
        for entry in reversed(msgs):
            if entry["body"] == text:
                return entry["message_id"]
        raise SwitchError(None, POST_MESSAGE, "no message id returned")

    async def send_targeted(self, to_agent: str, text: str) -> Any:
        """Send a targeted message to ``to_agent``.

        ``TARGETED_TO_KIND`` determines how the ``to_agent`` identifier is resolved.
        """
        # Resolve the target value based on the configured kind
        if TARGETED_TO_KIND == "name":
            target_val = to_agent
        elif TARGETED_TO_KIND == "id":
            if not self.agent_ids or to_agent not in self.agent_ids:
                raise SwitchError(None, SEND_TARGETED, f"no Switch id for {to_agent}")
            target_val = self.agent_ids[to_agent]
        elif TARGETED_TO_KIND == "names":
            target_val = [to_agent]
        elif TARGETED_TO_KIND == "ids":
            if not self.agent_ids or to_agent not in self.agent_ids:
                raise SwitchError(None, SEND_TARGETED, f"no Switch id for {to_agent}")
            target_val = [self.agent_ids[to_agent]]
        else:
            # Should never happen – defensive programming
            raise SwitchError(None, SEND_TARGETED, f"unknown TARGETED_TO_KIND {TARGETED_TO_KIND}")
        args = {TARGETED_TO_ARG: target_val, TARGETED_TEXT_ARG: text}
        result = await self.call(SEND_TARGETED, args)
        # Log a warning if the operation was not permitted but do not raise
        if isinstance(result, dict) and "not_permitted" in json.dumps(result):
            log.warning("send_targeted to %s was not permitted", to_agent)
        return result

    async def read_context(self, limit: int = 20) -> list[dict]:
        """Read recent context entries.

        Returns a flat list of messages ordered oldest‑first.
        """
        resp = await self.call(READ_CONTEXT, {READ_LIMIT_ARG: limit})
        threads = resp.get(READ_THREADS_KEY, [])
        entries: list[dict] = []
        for group in threads:
            root = group.get("root", {})
            entries.append({
                "message_id": root.get(CONTEXT_ID_KEY),
                "body": root.get(CONTEXT_BODY_KEY, ""),
                "sender": root.get(CONTEXT_SENDER_KEY, ""),
                "thread_id": None,
                "timestamp": root.get(CONTEXT_TIME_KEY, 0),
            })
            for reply in group.get("replies", []):
                entries.append({
                    "message_id": reply.get(CONTEXT_ID_KEY),
                    "body": reply.get(CONTEXT_BODY_KEY, ""),
                    "sender": reply.get(CONTEXT_SENDER_KEY, ""),
                    "thread_id": root.get(CONTEXT_ID_KEY),
                    "timestamp": reply.get(CONTEXT_TIME_KEY, 0),
                })
        # Filter to only messages (or entries without a kind field)
        entries = [e for e in entries if e.get("kind") in (None, "message")]
        # Sort by timestamp ascending, stable for ties
        entries.sort(key=lambda e: e["timestamp"])
        return entries

    async def upsert_room_doc(self, name: str, content: str) -> bool:
        """Create or update a room document.

        Returns ``True`` on success, ``False`` if the operation was a no‑op (e.g. document already exists).
        """
        if not DOCS_SUPPORTED:
            return False
        # Try cache first
        doc_id = self._doc_id_cache.get(name)
        if doc_id is None:
            # Need to discover existing docs via a connected room
            conn = await self.connect_room()
            for doc in conn.get("documents", []):
                if doc.get("name") == name:
                    doc_id = doc.get("id")
                    self._doc_id_cache[name] = doc_id
                    break
        if doc_id:
            try:
                await self.call(UPDATE_DOC, {DOC_ID_ARG: doc_id, "content": content})
                return True
            except SwitchError as exc:
                if exc.status == 404:
                    # Document vanished – fall through to create
                    self._doc_id_cache.pop(name, None)
                else:
                    raise
        # Create path
        payload = {DOC_NAME_ARG: name, DOC_CONTENT_ARG: content, **DOC_CREATE_EXTRA}
        try:
            result = await self.call(CREATE_DOC, payload)
            new_id = result.get(DOC_ID_KEY)
            if new_id:
                self._doc_id_cache[name] = new_id
                return True
            log.warning("create_room_document returned no id for %s", name)
            return False
        except SwitchError as exc:
            if exc.status == 409 or (
                isinstance(exc.detail, str) and "exist" in exc.detail.lower()
            ):
                log.warning("room document %s exists but its id is unknown", name)
                return False
            raise

    async def download(self, mxc: str, path_template: str) -> bytes:
        """Download a media attachment.

        ``path_template`` may contain ``{server_name}``, ``{mxc}``, ``{media_id}`` and ``{agent_id}``.
        """
        # Build URL according to spec – the path_template is a full URL with placeholders
        server_name = httpx.URL(self.server).host
        media_id = mxc.rsplit("/", 1)[-1]
        url = path_template.format(
            server_name=server_name,
            mxc=mxc,
            media_id=media_id,
            agent_id=self.agent_id,
        )
        hdrs = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = await self._client.get(url, headers=hdrs)
        except httpx.TransportError as exc:
            raise SwitchError(None, "download", str(exc) or type(exc).__name__)
        if resp.status_code >= 400:
            raise SwitchError(resp.status_code, "download", resp.text[:300])
        return resp.content

    async def aclose(self) -> None:
        await self._client.aclose()

    def __repr__(self) -> str:
        return f"OpsClient(agent_id={self.agent_id!r})"

