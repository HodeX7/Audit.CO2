"""The one small, swappable module the brief's architecture calls for
(Section 4: "called with a standard OpenAI-compatible client through one
small module, carbonroom/llm.py, so we can switch to Anthropic with one
setting"). Provider chosen by $LLM_PROVIDER ("nvidia", the free default,
or "anthropic"). Uses only the standard library (urllib/json) so running
this never requires installing an SDK, matching THIRD_PARTY.md's
stdlib-only claim.

This module is a plain text-in/text-out completion call. It is NEVER used
for arithmetic or for deciding a ledger value -- the Calculator/Checker/
Reporter never import this. Its only consumer so far is
carbonroom/check/nlu.py, which uses it to translate a loosely-phrased
human chat reply into one of resolve.py's fixed, already-validated
resolution strings -- never to invent a number or a fact.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path = _REPO_ROOT / ".env") -> None:
    """Minimal stdlib-only .env loader -- no python-dotenv dependency.
    Never overrides a variable already set in the real environment (a
    real `export` always wins over the file), so this is purely a
    convenience for local development, not a hidden override mechanism."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()  # drop inline comments
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


class LlmNotConfiguredError(RuntimeError):
    """Raised when no API key is set for the configured provider. Callers
    should treat this as 'the LLM path is unavailable,' and fall back to
    behavior that needs no model -- never silently retry or guess."""


class LlmCallError(RuntimeError):
    """Raised on a network/API failure. Same rule: fall back, don't guess."""


def is_configured() -> bool:
    provider = os.environ.get("LLM_PROVIDER", "nvidia").lower()
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return bool(os.environ.get("NVIDIA_API_KEY"))


def complete(prompt: str, *, system: str | None = None, max_tokens: int = 500) -> str:
    """Sends one prompt, returns the model's text reply. Raises
    LlmNotConfiguredError / LlmCallError rather than returning a fallback
    value -- the caller decides what "no answer" means for its own case,
    this module never papers over a failure with a guess.

    max_tokens defaults higher than you might expect for a one-line reply:
    some catalog models (e.g. NVIDIA's nemotron reasoning models) spend part
    of the budget on a hidden chain-of-thought before writing the actual
    answer. Too low a limit truncates before any real content is written,
    which _complete_nvidia() below treats as a hard failure, not a guess.
    """
    provider = os.environ.get("LLM_PROVIDER", "nvidia").lower()
    if provider == "anthropic":
        return _complete_anthropic(prompt, system=system, max_tokens=max_tokens)
    return _complete_nvidia(prompt, system=system, max_tokens=max_tokens)


def _post_json(url: str, headers: dict, body: dict, timeout: float = 20.0) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise LlmCallError(f"{url} returned HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from e
    except urllib.error.URLError as e:
        raise LlmCallError(f"could not reach {url}: {e}") from e


def _complete_nvidia(prompt: str, *, system: str | None, max_tokens: int) -> str:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmNotConfiguredError("NVIDIA_API_KEY is not set (LLM_PROVIDER=nvidia)")
    base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise LlmNotConfiguredError("LLM_MODEL is not set -- pick one from GET {NVIDIA_BASE_URL}/models")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    result = _post_json(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body={
            "model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0,
            # Our prompts are short classification/translation tasks that
            # never need chain-of-thought -- turn it off for models that
            # support this (e.g. nemotron) so max_tokens isn't silently
            # consumed by hidden reasoning before any real answer is written.
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    content = result["choices"][0]["message"].get("content")
    if not content:
        raise LlmCallError(
            f"model {model!r} returned no content (possibly truncated by max_tokens={max_tokens} "
            f"while reasoning). Raw message: {result['choices'][0]['message']!r}"
        )
    return content


def _complete_anthropic(prompt: str, *, system: str | None, max_tokens: int) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LlmNotConfiguredError("ANTHROPIC_API_KEY is not set (LLM_PROVIDER=anthropic)")
    model = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    result = _post_json(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        body=body,
    )
    blocks = result.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text:
        raise LlmCallError(f"model {model!r} returned no text content. Raw response: {result!r}")
    return text
