"""LLM path, fully mocked: proposals still have to pass the excerpt check; the cache makes runs keyless."""

from __future__ import annotations

import json
from types import SimpleNamespace

import openai
import pytest

from carbonroom import config, llm
from carbonroom.ingest import extract, pipeline
from carbonroom.ingest.hashing import sha256_file
from carbonroom.ledger import db

RENO_OCT = "2026-10_reno_electricity_ELB-RNO-2610.pdf"


def _reno_path():
    return config.seed_dir() / "later" / RENO_OCT


def _proposal(quantity="15.08", excerpt="Total energy used this period: 15.08 MWh"):
    return {
        "schema": "cr.extraction.v1",
        "doc_kind": "utility_bill",
        "doc_ref": {"value": "ELB-RNO-2610", "excerpt": "Bill number: ELB-RNO-2610", "page": 1},
        "site": {"value": "Reno Office", "excerpt": "Service location: Reno Office, 77 Ledger Lane", "page": 1},
        "period": {"value": "2026-10", "excerpt": "Service period: October 1, 2026 - October 31, 2026", "page": 1},
        "claims": [{"category": "electricity", "quantity": quantity, "unit": "MWh", "excerpt": excerpt, "page": 1}],
    }


@pytest.fixture
def fake_llm(monkeypatch):
    """Pretend a key is set and capture what the model would have been asked."""
    calls = []
    state = {"reply": _proposal(), "error": None}

    def chat_json(messages, model=None, **_):
        calls.append(messages)
        if state["error"]:
            raise state["error"]
        return json.loads(json.dumps(state["reply"])), llm.Provider("nvidia", "http://fake", "k", model or "fake/model")

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-fake")
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "chat_json", chat_json)
    return SimpleNamespace(calls=calls, state=state)


def _drop_cache(path):
    sha = sha256_file(path)
    for d in (config.extraction_cache_dir(), config.store_dir() / "extractions"):
        (d / f"{sha}.json").unlink(missing_ok=True)
    return sha


def test_llm_proposal_that_checks_out_is_stored_unverified(sites, fake_llm):
    sha = _drop_cache(_reno_path())
    r = pipeline.ingest_file(sites, _reno_path(), received_from="lena", room="cr-site-reno")
    assert r["proposer"] == "llm:nvidia:fake/model"
    (act,) = r["activities"]
    assert (act["quantity"], act["unit"], act["status"]) == ("15080", "kWh", "UNVERIFIED")
    assert "=== PAGE 1 ===" in fake_llm.calls[0][1]["content"]
    cached = json.loads((config.extraction_cache_dir() / f"{sha}.json").read_text())
    assert cached["proposer"] == "llm:nvidia:fake/model"


def test_hallucinated_number_becomes_a_gap_not_a_fact(sites, fake_llm):
    _drop_cache(_reno_path())
    fake_llm.state["reply"] = _proposal(quantity="16.08", excerpt="Total energy used this period: 16.08 MWh")
    r = pipeline.ingest_file(sites, _reno_path(), received_from="lena", room="cr-site-reno")
    assert r["activities"] == []
    assert db.list_activities(sites) == []
    gap = next(g for g in r["gaps"] if "16.08" in g["detail"])
    assert gap["kind"] == "unverified_claim" and gap["owner"] == "lena" and gap["room"] == "cr-site-reno"


def test_cache_is_used_without_any_key(sites, fake_llm, monkeypatch):
    _drop_cache(_reno_path())
    pipeline.ingest_file(sites, _reno_path(), received_from="lena")  # fills the cache via the fake LLM
    calls_before = len(fake_llm.calls)
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    proposed = extract.propose(_reno_path(), extract.read_pages(_reno_path()), sha256_file(_reno_path()))
    assert proposed.from_cache and proposed.proposer == "cache:llm:nvidia:fake/model"
    assert len(fake_llm.calls) == calls_before


def test_tampered_cache_still_fails_verification(sites):
    sha = sha256_file(_reno_path())
    cache_file = config.extraction_cache_dir() / f"{sha}.json"
    data = json.loads(cache_file.read_text())
    data["proposal"]["claims"][0]["quantity"] = "1.08"
    data["proposal"]["claims"][0]["excerpt"] = "Total energy used this period: 1.08 MWh"
    cache_file.write_text(json.dumps(data))
    r = pipeline.ingest_file(sites, _reno_path(), received_from="lena")
    assert r["activities"] == [] and r["gaps"]


def test_llm_failure_falls_back_to_rules_in_auto_mode(sites, fake_llm):
    _drop_cache(_reno_path())
    fake_llm.state["error"] = llm.LLMError("429 after 5 attempts")
    r = pipeline.ingest_file(sites, _reno_path(), received_from="lena")
    assert r["proposer"] == "rules-v1" and "used the rules proposer" in r["notes"][0]
    assert r["activities"][0]["quantity"] == "15080"


def test_llm_mode_without_key_is_an_error(sites, monkeypatch):
    _drop_cache(_reno_path())
    with pytest.raises(llm.LLMNotConfigured):
        extract.propose(_reno_path(), extract.read_pages(_reno_path()), sha256_file(_reno_path()), mode="llm")


def test_parse_json_object_variants():
    assert llm.parse_json_object('<think>hmm {"no": 1}</think>```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}
    assert llm.parse_json_object('Sure! {"x": [1, 2]} hope that helps') == {"x": [1, 2]}
    with pytest.raises(llm.LLMError):
        llm.parse_json_object("no json here")


def test_rate_limiter_spaces_calls():
    now = [100.0]
    slept = []

    def sleep(seconds):
        slept.append(round(seconds, 3))
        now[0] += seconds

    limiter = llm.RateLimiter(40, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.wait()
    assert slept == [1.5, 1.5]  # 60 s / 40 requests


def _rate_limit_error(retry_after: str) -> Exception:
    """A real openai.RateLimitError instance, built without the SDK's HTTP types (they differ by version)."""
    exc = openai.RateLimitError.__new__(openai.RateLimitError)
    Exception.__init__(exc, "slow down")
    exc.response = SimpleNamespace(headers={"retry-after": retry_after})
    return exc


class _FakeCompletions:
    def __init__(self, failures):
        self.failures = failures
        self.kwargs = []

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        if self.failures:
            self.failures -= 1
            raise _rate_limit_error(retry_after="2")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])


def _fake_client(failures=0):
    completions = _FakeCompletions(failures)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_chat_retries_429_using_retry_after(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("LLM_MODEL", "test/model")
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(1000, sleep=lambda s: None))
    client, completions = _fake_client(failures=2)
    slept = []
    data, provider = llm.chat_json([{"role": "user", "content": "hi"}], client=client, sleep=slept.append)
    assert data == {"ok": True} and slept == [2.0, 2.0] and len(completions.kwargs) == 3
    assert completions.kwargs[0]["temperature"] == 0 and provider.model == "test/model"


def test_anthropic_provider_omits_temperature(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(1000, sleep=lambda s: None))
    client, completions = _fake_client()
    _, provider = llm.chat([{"role": "user", "content": "hi"}], client=client)
    assert "temperature" not in completions.kwargs[0] and "response_format" not in completions.kwargs[0]
    assert provider.base_url == "https://api.anthropic.com/v1/"


def test_bench_scores_a_model_against_the_rules_baseline(seeded, fake_llm, capsys):
    from carbonroom.cli import main

    assert main(["llm", "bench", "--models", "fake/model"]) == 0
    out = capsys.readouterr().out
    assert "fake/model" in out and "EXACT" in out
    # the fake model always answers with the Reno October bill, which matches exactly one seed document
    assert "   1/13" in out


def test_models_command_without_key(env, capsys):
    from carbonroom.cli import main

    assert main(["llm", "models"]) == 2
    assert "NVIDIA_API_KEY" in capsys.readouterr().err


def _status_error(status: int, detail: str) -> Exception:
    exc = openai.APIStatusError.__new__(openai.APIStatusError)
    Exception.__init__(exc, f"Error code: {status}")
    exc.status_code, exc.body, exc.message = status, {"detail": detail}, f"Error code: {status}"
    return exc


class _FailingCompletions:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise self.exc


def test_no_default_model_means_not_configured(env, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert not llm.is_configured()  # auto mode then quietly uses the cache/rules
    with pytest.raises(llm.LLMNotConfigured, match="llm probe"):
        llm.provider()
    assert llm.provider(need_model=False).model == ""  # listing models still works


def test_retired_model_is_not_retried_and_says_why(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(1000, sleep=lambda s: None))
    completions = _FailingCompletions(_status_error(410, "Model meta/llama-3.3-70b-instruct is end-of-life"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = llm.probe("meta/llama-3.3-70b-instruct", client=client)
    assert completions.calls == 1
    assert result["ok"] is False and result["status"] == 410 and "end-of-life" in result["error"]


def test_probe_reports_a_working_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(1000, sleep=lambda s: None))
    client, _ = _fake_client()
    result = llm.probe("good/model", client=client)
    assert result["ok"] and result["json_ok"]


def test_chat_model_filter():
    assert llm.looks_like_chat_model("nvidia/nemotron-3-ultra-550b-a55b")
    assert llm.looks_like_chat_model("deepseek-ai/deepseek-v4.1-flash")
    for not_chat in ("nvidia/nemotron-3-embed-1b", "nvidia/nemotron-3.5-content-safety", "nvidia/nemotron-parse-2.0",
                     "nvidia/nemotron-4-340b-reward", "nvidia/llama-3.1-nemotron-safety-guard-8b-v3"):
        assert not llm.looks_like_chat_model(not_chat), not_chat


def test_bench_stops_early_on_an_unavailable_model(seeded, fake_llm, capsys):
    from carbonroom.cli import main

    fake_llm.state["error"] = llm.LLMError("nvidia API error 410 for old/model: end-of-life", status_code=410)
    assert main(["llm", "bench", "--models", "old/model"]) == 0
    assert len(fake_llm.calls) == 1
    assert "unavailable (HTTP 410)" in capsys.readouterr().out


def test_bench_skips_a_model_that_keeps_timing_out(seeded, fake_llm, capsys):
    from carbonroom.cli import main

    fake_llm.state["error"] = llm.LLMError("nvidia API failed after 2 attempts: Request timed out.")
    assert main(["llm", "bench", "--models", "slow/model"]) == 0
    assert len(fake_llm.calls) == 2
    assert "unreliable (2 failures in a row)" in capsys.readouterr().out


def test_attempts_and_timeout_come_from_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("LLM_MODEL", "test/model")
    monkeypatch.setenv("CR_LLM_ATTEMPTS", "2")
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(1000, sleep=lambda s: None))
    client, completions = _fake_client(failures=5)
    with pytest.raises(llm.LLMError, match="after 2 attempts"):
        llm.chat([{"role": "user", "content": "hi"}], client=client, sleep=lambda s: None)
    assert len(completions.kwargs) == 2
