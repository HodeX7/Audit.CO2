"""Model-agnostic JSON and phrasing boundary with replay-safe behavior."""

from __future__ import annotations

import json
import os
from typing import Any

from carbon_room.ledger import budget, connect

_client_factory = None


def set_client_factory(factory) -> None:
    """Inject a provider client for deterministic tests or an alternate model vendor."""
    global _client_factory
    _client_factory = factory


def _settings() -> tuple[str, float]:
    try:
        from carbon_room import config

        llm_settings = config.load_config().get("llm", {})
    except FileNotFoundError:
        llm_settings = {}
    return str(llm_settings.get("model", os.environ.get("CARBON_ROOM_MODEL", "claude-sonnet-4-5"))), float(llm_settings.get("temperature", 0))


def complete_json(task: str, system: str, user: Any, agent: str, close_id: str) -> dict:
    """Call an Anthropic-compatible client, retrying one invalid JSON response, then charge tokens."""
    model, temperature = _settings()
    if _client_factory is not None:
        client = _client_factory()
    else:
        try:
            from anthropic import Anthropic
        except ModuleNotFoundError as exc:
            raise RuntimeError("install project dependencies to use live model extraction") from exc
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    for attempt in range(2):
        response = client.messages.create(model=model, temperature=temperature, max_tokens=2048, system=system,
                                          messages=[{"role": "user", "content": json.dumps(user, default=str)}])
        text = response.content[0].text
        try:
            decoded = json.loads(text)
            usage = getattr(response, "usage", None)
            tokens = int(getattr(usage, "input_tokens", 0)) + int(getattr(usage, "output_tokens", 0))
            if close_id:
                with connect() as db:
                    budget.charge(db, close_id, agent, tokens)
            return decoded
        except json.JSONDecodeError:
            if attempt:
                raise ValueError(f"model returned invalid JSON for task {task!r}")
    raise AssertionError("unreachable")


def phrase(question: str, facts: list[str], agent: str, close_id: str, *, scope: str = "this close",
           reason: str = "no VERIFIED ledger rows match", owner: str = "lead") -> str:
    """Never invoke a model when the truth set is empty."""
    if not facts:
        return f"UNKNOWN for {scope}, because {reason}, owned by {owner}"
    return "Verified ledger facts: " + "; ".join(facts)
