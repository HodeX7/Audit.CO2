"""Model-agnostic provider layer: any model plugs in by settings, or by a few lines of adapter code."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from carbonroom import config, llm
from carbonroom.cli import main
from carbonroom.ingest import pipeline
from carbonroom.ingest.hashing import sha256_file

ALL_LLM_VARS = ["LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_TEMPERATURE", "LLM_MODEL_EXTRACT",
                "LLM_PROVIDER_EXTRACT", "NVIDIA_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"]


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    for name in ALL_LLM_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(10_000, sleep=lambda s: None))


class FakeCompletions:
    def __init__(self, reply='{"ok": true}', error: Exception | None = None):
        self.reply, self.error, self.kwargs = reply, error, []

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


def fake_client(reply='{"ok": true}', error=None):
    completions = FakeCompletions(reply, error)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


@pytest.mark.parametrize(
    "name, key_var, base_url, temperature",
    [
        ("nvidia", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1", 0),
        ("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/", None),
        ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", None),
        ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", 0),
    ],
)
def test_hosted_presets(monkeypatch, name, key_var, base_url, temperature):
    monkeypatch.setenv("LLM_PROVIDER", name)
    monkeypatch.setenv("LLM_MODEL", "some/model")
    with pytest.raises(llm.LLMNotConfigured, match=key_var):
        llm.provider()
    monkeypatch.setenv(key_var, "k-123")
    p = llm.provider()
    assert (p.base_url, p.api_key, p.model, p.temperature) == (base_url, "k-123", "some/model", temperature)


def test_local_ollama_needs_no_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    p = llm.provider()
    assert p.base_url == "http://localhost:11434/v1" and p.api_key == llm.NO_KEY


def test_any_openai_compatible_server(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "my-model")
    with pytest.raises(llm.LLMNotConfigured, match="LLM_BASE_URL"):
        llm.provider()
    monkeypatch.setenv("LLM_BASE_URL", "http://gpu-box:8000/v1")
    assert llm.provider().base_url == "http://gpu-box:8000/v1" and llm.provider().api_key == llm.NO_KEY
    monkeypatch.setenv("LLM_API_KEY", "secret")
    assert llm.provider().api_key == "secret"


def test_generic_overrides_beat_presets(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_BASE_URL", "https://proxy.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "proxy-key")
    p = llm.provider()
    assert (p.name, p.base_url, p.api_key) == ("nvidia", "https://proxy.example/v1", "proxy-key")


def test_per_task_settings(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("LLM_MODEL", "big/model")
    monkeypatch.setenv("LLM_MODEL_EXTRACT", "fast/model")
    assert llm.provider().model == "big/model"
    assert llm.provider(task="extract").model == "fast/model"
    monkeypatch.setenv("LLM_PROVIDER_EXTRACT", "ollama")
    assert llm.provider(task="extract").name == "ollama" and llm.provider().name == "nvidia"


@pytest.mark.parametrize("setting, sent", [(None, 0), ("none", "absent"), ("0.2", 0.2)])
def test_temperature_setting(monkeypatch, setting, sent):
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("LLM_MODEL", "m")
    if setting is not None:
        monkeypatch.setenv("LLM_TEMPERATURE", setting)
    client, completions = fake_client()
    llm.chat([{"role": "user", "content": "hi"}], client=client)
    assert completions.kwargs[0].get("temperature", "absent") == sent


def test_unknown_provider_lists_the_options(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "skynet")
    with pytest.raises(llm.LLMNotConfigured, match="ollama"):
        llm.provider()


@pytest.fixture
def custom_provider():
    """A provider that does NOT speak the OpenAI API, plugged in with a tiny adapter."""
    reply = {
        "doc_kind": "utility_bill",
        "site": {"value": "Reno Office", "excerpt": "Service location: Reno Office, 77 Ledger Lane", "page": 1},
        "period": {"value": "2026-10", "excerpt": "Service period: October 1, 2026 - October 31, 2026", "page": 1},
        "claims": [{"category": "electricity", "quantity": "15.08", "unit": "MWh",
                    "excerpt": "Total energy used this period: 15.08 MWh", "page": 1}],
    }
    state = {"calls": 0, "error": None}

    class HomegrownSDK:  # e.g. a vendor SDK with its own method names
        def generate(self, prompt: str) -> str:
            state["calls"] += 1
            if state["error"]:
                raise state["error"]
            return json.dumps(reply)

    def adapter(p: llm.Provider):
        sdk = HomegrownSDK()

        def create(**kwargs):
            text = sdk.generate("\n".join(m["content"] for m in kwargs["messages"]))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    llm.register_provider("homegrown", base_url="local://", key_env=None, temperature=None, client_factory=adapter)
    yield state
    llm.PROVIDERS.pop("homegrown")


def _reno_oct():
    path = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    (config.extraction_cache_dir() / f"{sha256_file(path)}.json").unlink(missing_ok=True)
    return path


def test_a_plugged_in_provider_drives_extraction_end_to_end(sites, custom_provider, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_EXTRACT", "homegrown")
    monkeypatch.setenv("LLM_MODEL_EXTRACT", "tiny-model")
    r = pipeline.ingest_file(sites, _reno_oct(), received_from="lena", proposer="llm")
    assert r["proposer"] == "llm:homegrown:tiny-model" and custom_provider["calls"] == 1
    assert r["activities"][0]["quantity"] == "15080"  # still verified against the PDF


def test_a_failing_plugged_in_provider_falls_back_to_rules(sites, custom_provider, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "homegrown")
    monkeypatch.setenv("LLM_MODEL", "tiny-model")
    custom_provider["error"] = ConnectionResetError("socket closed")
    r = pipeline.ingest_file(sites, _reno_oct(), received_from="lena")
    assert r["proposer"] == "rules-v1" and "homegrown client error" in r["notes"][0]


def test_providers_command(env, capsys, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert main(["llm", "providers"]) == 0
    out = capsys.readouterr().out
    for name in ("nvidia", "anthropic", "openai", "openrouter", "ollama", "openai_compatible"):
        assert name in out
    assert "* openrouter" in out
    assert main(["llm", "providers", "--json"]) == 0
    assert {r["name"] for r in json.loads(capsys.readouterr().out)} >= {"ollama", "openai_compatible"}


def test_provider_flag_switches_provider_for_one_run(env, capsys, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")  # restored after the test
    seen = []
    monkeypatch.setattr(llm, "probe", lambda model: seen.append(llm.provider(model).name) or
                        {"model": model, "ok": True, "status": 200, "json_ok": True, "seconds": 0.1, "error": None})
    assert main(["llm", "probe", "--provider", "ollama", "--models", "llama3.2"]) == 0
    assert seen == ["ollama"]
