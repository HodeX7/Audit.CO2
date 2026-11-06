"""JSON model boundary with an optional vendor-neutral completion provider."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from typing import Any

from carbon_room.ledger import budget, connect

_client_factory = None
_completion_provider: Callable[..., tuple[dict[str, Any], int]] | None = None


def set_client_factory(factory) -> None:
    """Inject an Anthropic-compatible client for deterministic tests."""
    global _client_factory
    _client_factory = factory


def set_completion_provider(provider: Callable[..., tuple[dict[str, Any], int]] | None) -> None:
    """Set a vendor-neutral JSON provider returning ``(object, token_count)``.

    Providers receive task, system, user, model, temperature, max_tokens, and
    timeout_seconds as keyword arguments. This keeps the application independent
    of SDK-specific response objects while retaining Anthropic as the default.
    """
    global _completion_provider
    _completion_provider = provider


def _settings() -> tuple[str, float, float]:
    try:
        from carbon_room import config

        llm_settings = config.load_config().get("llm", {})
    except FileNotFoundError:
        llm_settings = {}
    model = str(llm_settings.get("model", os.environ.get("CARBON_ROOM_MODEL", "claude-sonnet-4-5")))
    temperature = float(llm_settings.get("temperature", 0))
    timeout_seconds = float(llm_settings.get("timeout_seconds", 30))
    if timeout_seconds <= 0:
        raise ValueError("llm.timeout_seconds must be positive")
    return model, temperature, timeout_seconds


def complete_json(task: str, system: str, user: Any, agent: str, close_id: str,
                  *, conn: sqlite3.Connection | None = None) -> dict:
    """Request JSON through the configured provider and charge the active ledger once."""
    model, temperature, timeout_seconds = _settings()
    if _completion_provider is not None:
        decoded, tokens = _completion_provider(
            task=task, system=system, user=user, model=model, temperature=temperature,
            max_tokens=2048, timeout_seconds=timeout_seconds,
        )
        if not isinstance(decoded, dict):
            raise ValueError(f"model returned a non-object JSON response for task {task!r}")
        _charge(conn, close_id, agent, tokens)
        return decoded
    if _client_factory is not None:
        client = _client_factory()
    else:
        try:
            from anthropic import Anthropic
        except ModuleNotFoundError as exc:
            raise RuntimeError("install project dependencies to use live model extraction") from exc
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"), timeout=timeout_seconds)
    for attempt in range(2):
        response = client.messages.create(model=model, temperature=temperature, max_tokens=2048, system=system,
                                          messages=[{"role": "user", "content": json.dumps(user, default=str)}])
        try:
            text = response.content[0].text
        except (AttributeError, IndexError, TypeError) as exc:
            raise ValueError(f"model returned an invalid response for task {task!r}") from exc
        try:
            decoded = json.loads(text)
            if not isinstance(decoded, dict):
                raise ValueError(f"model returned a non-object JSON response for task {task!r}")
            usage = getattr(response, "usage", None)
            tokens = int(getattr(usage, "input_tokens", 0)) + int(getattr(usage, "output_tokens", 0))
            _charge(conn, close_id, agent, tokens)
            return decoded
        except json.JSONDecodeError:
            if attempt:
                raise ValueError(f"model returned invalid JSON for task {task!r}")
    raise AssertionError("unreachable")


def _charge(conn: sqlite3.Connection | None, close_id: str, agent: str, tokens: int) -> None:
    """Charge only after a validated response, using the caller's transaction when supplied."""
    if not close_id:
        return
    if conn is not None:
        budget.charge(conn, close_id, agent, tokens)
        return
    with connect() as db:
        budget.charge(db, close_id, agent, tokens)


def phrase(question: str, facts: list[str], agent: str, close_id: str, *, scope: str = "this close",
           reason: str = "no VERIFIED ledger rows match", owner: str = "lead") -> str:
    """Never invoke a model when the truth set is empty."""
    if not facts:
        return f"UNKNOWN for {scope}, because {reason}, owned by {owner}"
    return "Verified ledger facts: " + "; ".join(facts)
