"""One small, model-agnostic door to any language model.

Any provider that speaks the OpenAI chat-completions API works by settings alone:

  LLM_PROVIDER        preset        base URL                                  key
  nvidia (default)    free trial    https://integrate.api.nvidia.com/v1       NVIDIA_API_KEY (NVIDIA_BASE_URL overrides)
  anthropic           Claude        https://api.anthropic.com/v1/             ANTHROPIC_API_KEY (CR_ANTHROPIC_BASE_URL)
  openai              OpenAI        https://api.openai.com/v1                 OPENAI_API_KEY
  openrouter          many vendors  https://openrouter.ai/api/v1              OPENROUTER_API_KEY
  ollama              local models  http://localhost:11434/v1                 none
  openai_compatible   anything else LLM_BASE_URL (required)                   LLM_API_KEY (optional)

LLM_BASE_URL / LLM_API_KEY override any preset, LLM_TEMPERATURE sets or disables temperature, and each
setting can be overridden per task: LLM_MODEL_EXTRACT, LLM_PROVIDER_EXTRACT, ... (task "extract" is
document extraction; teammates may use their own task names). A provider that does not speak this API
can be plugged in with register_provider(..., client_factory=...).

The model only PROPOSES extracted fields. It never does arithmetic, and code accepts a proposal only
after the excerpt is found in the document (carbonroom/ingest/extract.py) - which is what makes it safe
to swap models.

Sources: NVIDIA NIM FAQ (about 40 requests/minute, 429 + Retry-After); Claude docs "OpenAI SDK
compatibility" (temperature < 1 and response_format=json_object are rejected on recent models);
OpenRouter docs (base URL https://openrouter.ai/api/v1); Ollama "OpenAI compatibility" blog
(http://localhost:11434/v1, api_key required but unused).
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from carbonroom import config

TASK_OVERRIDE_FIELDS = ("PROVIDER", "MODEL", "BASE_URL", "API_KEY", "TEMPERATURE")
KNOWN_TASKS = ("extract",)
NO_KEY = "not-needed"  # the openai client requires a non-empty key even for local servers


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str | None
    key_env: str | None  # None = no key needed
    base_env: str | None = None
    temperature: float | None = 0  # None = never send temperature
    default_model: str | None = None
    client_factory: Callable[["Provider"], Any] | None = None  # None = the openai client
    note: str = ""


PROVIDERS: dict[str, ProviderSpec] = {}


def register_provider(
    name: str,
    *,
    base_url: str | None = None,
    key_env: str | None = None,
    base_env: str | None = None,
    temperature: float | None = 0,
    default_model: str | None = None,
    client_factory: Callable[["Provider"], Any] | None = None,
    note: str = "",
) -> ProviderSpec:
    """Add (or replace) a provider preset. `client_factory(provider)` must return an object with
    `.chat.completions.create(**kwargs)` returning an OpenAI-shaped response (and optionally
    `.models.list()`), so any SDK can be wrapped in a few lines."""
    spec = ProviderSpec(name, base_url, key_env, base_env, temperature, default_model, client_factory, note)
    PROVIDERS[name] = spec
    return spec


# No default models: hosted models get retired (meta/llama-3.3-70b-instruct returned HTTP 410 on NVIDIA on
# 2026-11-03). Pick one with `carbonroom llm probe` + `carbonroom llm bench` and set LLM_MODEL.
register_provider("nvidia", base_url="https://integrate.api.nvidia.com/v1", key_env="NVIDIA_API_KEY",
                  base_env="NVIDIA_BASE_URL", note="free trial; about 40 requests/minute")
register_provider("anthropic", base_url="https://api.anthropic.com/v1/", key_env="ANTHROPIC_API_KEY",
                  base_env="CR_ANTHROPIC_BASE_URL",  # not ANTHROPIC_BASE_URL: Claude Code may set that
                  temperature=None, note="OpenAI SDK compatibility layer; no temperature")
register_provider("openai", base_url="https://api.openai.com/v1", key_env="OPENAI_API_KEY", temperature=None,
                  note="no temperature (reasoning models reject it)")
register_provider("openrouter", base_url="https://openrouter.ai/api/v1", key_env="OPENROUTER_API_KEY",
                  note="one key, many vendors' models")
register_provider("ollama", base_url="http://localhost:11434/v1", key_env=None,
                  note="local models, no key, no network")
register_provider("openai_compatible", base_url=None, key_env=None,
                  note="any OpenAI-compatible server: set LLM_BASE_URL (and LLM_API_KEY if it needs one)")


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
    temperature: float | None = 0
    task: str | None = None
    spec: ProviderSpec | None = field(default=None, compare=False, repr=False)

    @property
    def label(self) -> str:
        return f"llm:{self.name}:{self.model}"


def setting(name: str, task: str | None = None, default: str | None = None) -> str | None:
    """LLM_<NAME>_<TASK> if set, else LLM_<NAME>, else default."""
    if task:
        value = config.env(f"LLM_{name}_{task.upper()}")
        if value is not None:
            return value
    return config.env(f"LLM_{name}", default)


def _temperature(spec: ProviderSpec, task: str | None) -> float | None:
    raw = setting("TEMPERATURE", task)
    if raw is None:
        return spec.temperature
    if raw.strip().lower() in ("none", "off", "unset", ""):
        return None
    return float(raw)


def provider(model: str | None = None, *, need_model: bool = True, task: str | None = None) -> Provider:
    """Resolve provider, base URL, key, model and temperature from the environment (per task if given)."""
    name = (setting("PROVIDER", task, "nvidia") or "nvidia").lower()
    if name not in PROVIDERS:
        raise LLMNotConfigured(f"LLM_PROVIDER={name!r} is not supported; use one of {', '.join(sorted(PROVIDERS))}")
    spec = PROVIDERS[name]
    base_url = setting("BASE_URL", task) or (config.env(spec.base_env) if spec.base_env else None) or spec.base_url
    if not base_url:
        raise LLMNotConfigured(f"LLM_PROVIDER={name} needs LLM_BASE_URL")
    key = setting("API_KEY", task) or (config.env(spec.key_env) if spec.key_env else None)
    if spec.key_env and not key:
        raise LLMNotConfigured(f"{spec.key_env} is not set")
    chosen = model or setting("MODEL", task, spec.default_model)
    if need_model and not chosen:
        raise LLMNotConfigured("LLM_MODEL is not set; find a working one with `carbonroom llm probe`, "
                               "then compare with `carbonroom llm bench`")
    return Provider(name=name, base_url=base_url, api_key=key or NO_KEY, model=chosen or "",
                    temperature=_temperature(spec, task), task=task, spec=spec)


def is_configured(task: str | None = None) -> bool:
    try:
        provider(task=task)
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
    if p.spec is not None and p.spec.client_factory is not None:
        return p.spec.client_factory(p)
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
    task: str | None = None,
    max_tokens: int = 1500,
    attempts: int | None = None,
    client: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, Provider]:
    """Send a chat completion with throttling and retries. Returns (text, provider)."""
    import openai

    p = provider(model, task=task)
    cli = client or _client(p)
    attempts = attempts or int(config.env("CR_LLM_ATTEMPTS", "3"))
    kwargs: dict[str, Any] = {"model": p.model, "messages": messages, "max_tokens": max_tokens}
    if p.temperature is not None:
        kwargs["temperature"] = p.temperature
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
        except Exception as exc:  # noqa: BLE001 - a plugged-in client failed; let auto mode fall back
            raise LLMError(f"{p.name} client error for {p.model}: {exc}") from exc
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


def describe_providers() -> list[dict[str, Any]]:
    """Every preset, whether it is configured right now, and which one is active."""
    active = (setting("PROVIDER", None, "nvidia") or "nvidia").lower()
    rows = []
    for name, spec in sorted(PROVIDERS.items()):
        key_ok = spec.key_env is None or bool(setting("API_KEY") or config.env(spec.key_env))
        rows.append({
            "name": name,
            "active": name == active,
            "base_url": (config.env(spec.base_env) if spec.base_env else None) or spec.base_url or "LLM_BASE_URL",
            "key_env": spec.key_env or "-",
            "key_set": key_ok,
            "temperature": spec.temperature,
            "note": spec.note,
        })
    return rows


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
