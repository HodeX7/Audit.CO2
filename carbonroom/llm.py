"""One small door to the language model.

Provider is chosen by LLM_PROVIDER:
  nvidia     (default, free trial) -> https://integrate.api.nvidia.com/v1, key NVIDIA_API_KEY
  anthropic  (optional)            -> https://api.anthropic.com/v1/ (OpenAI SDK compatibility layer),
                                      key ANTHROPIC_API_KEY

Both are called with the standard `openai` client, so switching is one setting.
The model only PROPOSES extracted fields. It never does arithmetic, and code accepts a
proposal only after the excerpt is found in the document (carbonroom/ingest/extract.py).

Rate limits: NVIDIA's free tier allows about 40 requests/minute per account and returns
HTTP 429 with Retry-After when exceeded. We throttle to CR_LLM_RPM (default 35) and retry
with backoff. Sources: NVIDIA developer forum NIM FAQ; docs.claude.com OpenAI SDK compatibility
page (which says temperature < 1 and response_format=json_object are rejected on recent Claude
models, so we send neither to Anthropic).
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from carbonroom import config

PROVIDERS = {
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "base_env": "NVIDIA_BASE_URL",
        # No default: NVIDIA retires hosted models (meta/llama-3.3-70b-instruct returned HTTP 410 on
        # 2026-11-03) and some listed models answer 404. Pick one with `carbonroom llm probe` + `llm bench`.
        "default_model": None,
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/",
        "key_env": "ANTHROPIC_API_KEY",
        "base_env": "CR_ANTHROPIC_BASE_URL",  # not ANTHROPIC_BASE_URL: Claude Code may set that
        "default_model": "claude-haiku-5-5",
    },
}


class LLMError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# HTTP statuses that mean "this model/key won't work"; retrying or trying more documents is pointless.
UNAVAILABLE_STATUS = {401, 403, 404, 410}


class LLMNotConfigured(LLMError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str

    @property
    def label(self) -> str:
        return f"llm:{self.name}:{self.model}"


def provider(model: str | None = None, *, need_model: bool = True) -> Provider:
    name = (config.env("LLM_PROVIDER", "nvidia") or "nvidia").lower()
    if name not in PROVIDERS:
        raise LLMNotConfigured(f"LLM_PROVIDER={name!r} is not supported (use nvidia or anthropic)")
    spec = PROVIDERS[name]
    key = config.env(spec["key_env"])
    if not key:
        raise LLMNotConfigured(f"{spec['key_env']} is not set")
    chosen = model or config.env("LLM_MODEL", spec["default_model"])
    if need_model and not chosen:
        raise LLMNotConfigured("LLM_MODEL is not set; find a working one with `carbonroom llm probe`, "
                               "then compare with `carbonroom llm bench`")
    return Provider(
        name=name,
        base_url=config.env(spec["base_env"], spec["base_url"]),
        api_key=key,
        model=chosen or "",
    )


def is_configured() -> bool:
    try:
        provider()
    except LLMNotConfigured:
        return False
    return True


class RateLimiter:
    """Spaces calls at least 60/rpm seconds apart (shared by every thread in this process)."""

    def __init__(self, rpm: float, clock: Callable[[], float] = time.monotonic, sleep=time.sleep):
        self.interval = 60.0 / max(rpm, 1.0)
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if now < self._next:
                self._sleep(self._next - now)
                now = self._next
            self._next = now + self.interval


_LIMITER: RateLimiter | None = None


def limiter() -> RateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = RateLimiter(float(config.env("CR_LLM_RPM", "35")))
    return _LIMITER


def _client(p: Provider):
    from openai import OpenAI

    # NVIDIA's free endpoints sometimes hang; a short timeout + few attempts keeps a stuck model from
    # blocking an upload for minutes (auto mode then falls back to the rules proposer).
    timeout = float(config.env("CR_LLM_TIMEOUT", "45"))
    return OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=timeout, max_retries=0)


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    value = headers.get("retry-after") if hasattr(headers, "get") else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int = 1500,
    attempts: int | None = None,
    client: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, Provider]:
    """Send a chat completion with throttling and retries. Returns (text, provider)."""
    import openai

    p = provider(model)
    cli = client or _client(p)
    attempts = attempts or int(config.env("CR_LLM_ATTEMPTS", "3"))
    kwargs: dict[str, Any] = {"model": p.model, "messages": messages, "max_tokens": max_tokens}
    if p.name == "nvidia":
        kwargs["temperature"] = 0
    last: Exception | None = None
    for attempt in range(attempts):
        limiter().wait()
        try:
            resp = cli.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or ""), p
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                openai.InternalServerError) as exc:
            last = exc
            delay = _retry_after(exc) or min(30.0, 2.0 * (2**attempt))
            sleep(delay)
        except openai.APIStatusError as exc:  # 4xx other than 429: not retryable
            raise LLMError(f"{p.name} API error {exc.status_code} for {p.model}: {_error_detail(exc)}",
                           status_code=exc.status_code) from exc
    raise LLMError(f"{p.name} API failed after {attempts} attempts: {last}")


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (handles ```json fences and <think> blocks)."""
    text = _THINK.sub("", text).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    if start < 0:
        raise LLMError("model reply contained no JSON object")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise LLMError("model reply had an unterminated JSON object")


def chat_json(messages: list[dict[str, Any]], **kwargs: Any) -> tuple[dict[str, Any], Provider]:
    text, p = chat(messages, **kwargs)
    return parse_json_object(text), p


def _error_detail(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        for key in ("detail", "message", "error", "title"):
            if body.get(key):
                return str(body[key])[:240]
    return str(getattr(exc, "message", exc))[:240]


def list_models() -> list[str]:
    p = provider(need_model=False)
    return sorted(m.id for m in _client(p).models.list().data)


# Model ids that are clearly not chat/instruct models (embeddings, guards, OCR, speech, ...).
_NOT_CHAT = re.compile(
    r"embed|safety|guard|reward|parse|rerank|retriev|clip|ocr|asr|tts|speech|audio|translat|detector|"
    r"segment|diffusion|flux|sdxl|cosmos|pii|topic-control|content-safety|bge|e5-|nv-dino|deplot|coder",
    re.IGNORECASE,
)


def looks_like_chat_model(model_id: str) -> bool:
    return not _NOT_CHAT.search(model_id)


def probe(model: str, *, client: Any = None, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """One tiny call: does this model answer chat completions for this key, and does it return JSON?"""
    started = time.monotonic()
    messages = [{"role": "user", "content": 'Reply with exactly this JSON and nothing else: {"ok": true}'}]
    try:
        text, _ = chat(messages, model=model, max_tokens=600, attempts=2, client=client, sleep=sleep)
    except LLMError as exc:
        return {"model": model, "ok": False, "status": exc.status_code, "json_ok": False,
                "seconds": round(time.monotonic() - started, 1), "error": str(exc)}
    try:
        json_ok = parse_json_object(text).get("ok") is True
    except (LLMError, json.JSONDecodeError):
        json_ok = False
    return {"model": model, "ok": True, "status": 200, "json_ok": json_ok,
            "seconds": round(time.monotonic() - started, 1), "error": None}
