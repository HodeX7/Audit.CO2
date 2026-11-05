"""Model adapter: extract and phrase only. Phrasing can't change a fact, budgets cap spend per agent per close,
and replay mode reproduces a run from the cache alone."""

from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest

from carbonroom import budgets, config, llm
from carbonroom.cli import main
from carbonroom.ingest import batch, pipeline
from carbonroom.ledger import db

MESSAGE = ("Collected 11 documents for 2026-10 (0 duplicate). 10 activities, all UNVERIFIED. "
           "Still missing: Reno Office electricity, owner @lena (GAP-012).")


class FakeClient:
    def __init__(self, *replies, tokens=100):
        self.replies, self.tokens, self.calls = list(replies), tokens, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if self.replies else "ok"
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
                               usage=SimpleNamespace(total_tokens=self.tokens))


@pytest.fixture
def model(env, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")  # no key needed
    monkeypatch.setenv("LLM_MODEL", "test/model")
    monkeypatch.setattr(llm, "_LIMITER", llm.RateLimiter(1_000_000))
    return env


# --- phrase ---------------------------------------------------------------------------------------------


def test_phrasing_is_off_unless_asked(model):
    out = llm.phrase(MESSAGE, client=FakeClient("anything"))
    assert (out.text, out.phrased) == (MESSAGE, False)


def test_a_faithful_rewording_is_used(model, monkeypatch):
    monkeypatch.setenv("CR_PHRASE", "auto")
    reworded = ("I collected 11 documents for 2026-10 with 0 duplicate: 10 activities, all UNVERIFIED. "
                "Reno Office electricity is still missing - @lena owns GAP-012.")
    client = FakeClient(f"<think>plan</think>{reworded}")
    out = llm.phrase(MESSAGE, question="did you get everything?", client=client)
    assert (out.text, out.phrased, out.model) == (reworded, True, "test/model")
    assert "did you get everything?" in client.calls[0]["messages"][1]["content"]


@pytest.mark.parametrize("reply, what", [
    ("I collected 12 documents for 2026-10 (0 duplicate). 10 activities, all UNVERIFIED. Reno Office electricity "
     "is missing, @lena (GAP-012).", "numbers"),                                    # changed a number
    ("I collected 11 documents for 2026-10 (0 duplicate). 10 activities, all UNVERIFIED. Reno Office electricity "
     "is missing, @lena.", "ids"),                                                   # dropped the gap id
    ("I collected 11 documents for 2026-10 (0 duplicate). 10 activities, all VERIFIED. Reno Office electricity "
     "is missing, @lena (GAP-012).", "statuses"),                                   # changed a status
    ("I collected 11 documents for 2026-10 (0 duplicate): 10 activities, all UNVERIFIED, about 42.1 tCO2e. "
     "Reno Office electricity is missing, @lena (GAP-012).", "numbers"),            # invented a total
    ("I collected 11 documents for 2026-09 (0 duplicate). 10 activities, all UNVERIFIED. Reno Office electricity "
     "is missing, @lena (GAP-012).", "months"),                                     # wrong month
    ("I collected 11 documents for 2026-10 (0 duplicate). 10 activities, all UNVERIFIED. Reno Office electricity "
     "is missing, @omar (GAP-012).", "handles"),                                    # wrong owner
])
def test_a_rewording_that_changes_any_fact_is_refused(model, monkeypatch, reply, what):
    monkeypatch.setenv("CR_PHRASE", "auto")
    out = llm.phrase(MESSAGE, client=FakeClient(reply))
    assert (out.text, out.phrased) == (MESSAGE, False)
    assert out.reason.startswith("model changed facts") and what in out.reason


def test_no_model_or_a_failing_model_keeps_the_plain_message(model, monkeypatch):
    monkeypatch.setenv("CR_PHRASE", "auto")
    out = llm.phrase(MESSAGE, client=FakeClient(llm.LLMError("boom")))
    assert (out.text, out.phrased) == (MESSAGE, False) and "model unavailable" in out.reason
    monkeypatch.delenv("LLM_MODEL")
    out = llm.phrase(MESSAGE, client=FakeClient("x"))
    assert (out.text, out.phrased, out.reason) == (MESSAGE, False, "no model configured for phrasing")


def test_phrase_uses_its_own_model_setting(model, monkeypatch):
    monkeypatch.setenv("CR_PHRASE", "auto")
    monkeypatch.setenv("LLM_MODEL_PHRASE", "small/fast")
    client = FakeClient(MESSAGE)
    assert llm.phrase(MESSAGE, client=client).model == "small/fast"
    assert client.calls[0]["model"] == "small/fast"


# --- budgets --------------------------------------------------------------------------------------------


def test_a_budget_warns_once_then_stops_calls(model):
    seen = []
    budget = llm.Budget("cr-collector", "CLOSE-2026-10-v1", cap=300, warn_at=0.5,
                        record=lambda tokens, info, warn, exhausted: seen.append((tokens, warn, exhausted)))
    client = FakeClient("a", "b", "c", "d", tokens=100)
    with llm.budget_scope(budget):
        for _ in range(3):
            llm.chat([{"role": "user", "content": "hi"}], client=client)
        with pytest.raises(llm.BudgetExceeded, match="300"):
            llm.chat([{"role": "user", "content": "hi"}], client=client)
    assert seen == [(100, False, False), (100, True, False), (100, False, True)]
    assert len(client.calls) == 3  # the 4th call never reached the model
    llm.chat([{"role": "user", "content": "outside"}], client=client)  # no scope, no cap


def test_the_tally_lives_in_the_ledger_and_survives_a_restart(model):
    main(["seed"])
    conn = db.connect()
    close = db.start_close(conn, "2026-10", actor="maya", factor_set="egrid-2024")
    with budgets.scope(conn, close["id"], "cr-collector", cap=250) as b:
        llm.chat([{"role": "user", "content": "one"}], client=FakeClient("x", tokens=120), task="extract")
        llm.chat([{"role": "user", "content": "two"}], client=FakeClient("x", tokens=120), task="phrase")
    assert budgets.used(conn, close["id"], "cr-collector") == 240 == b.used
    with budgets.scope(conn, close["id"], "cr-collector", cap=250) as again:  # a new process would see this
        assert again.used == 240
        llm.chat([{"role": "user", "content": "three"}], client=FakeClient("x", tokens=20))
        with pytest.raises(llm.BudgetExceeded):
            llm.chat([{"role": "user", "content": "four"}], client=FakeClient("x"))
    actions = [r["action"] for r in conn.execute("SELECT action FROM events WHERE ref = ? ORDER BY id", (close["id"],))]
    assert actions.count("llm_usage") == 3
    assert actions.count("budget_warning") == 1 and actions.count("budget_exhausted") == 1
    usage = db.row_to_dict(conn.execute("SELECT * FROM events WHERE action='llm_usage' ORDER BY id").fetchone())
    assert usage["detail"] == {"task": "extract", "model": "test/model", "provider": "ollama", "tokens": 120}
    assert budgets.report(conn, close["id"]) == [{"agent": "cr-collector", "calls": 3, "tokens": 260,
                                                   "cap": budgets.cap_tokens(), "warned": True, "exhausted": True}]
    assert db.verify_audit_chain(conn)["ok"]


def test_a_spent_budget_makes_extraction_fall_back_not_fail(model, monkeypatch):
    from carbonroom.ingest import extract

    monkeypatch.setattr(extract, "llm_propose", lambda *a, **k: (_ for _ in ()).throw(
        llm.BudgetExceeded("cr-collector has used 200,000 of 200,000 tokens")))
    path = config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf"
    proposed = extract.propose(path, extract.read_pages(path), "0" * 64, mode="auto", refresh=True)
    assert proposed.proposer == "rules-v1" and "200,000" in proposed.notes[0]


def test_worker_threads_charge_the_same_budget(model, monkeypatch):
    main(["seed"])
    conn = db.connect()
    close = db.start_close(conn, "2026-10", actor="maya", factor_set="egrid-2024")
    seen = []
    real = pipeline.prepare

    def spy(inc, **kw):
        seen.append(llm.current_budget())
        return real(inc, **kw)

    monkeypatch.setattr(pipeline, "prepare", spy)
    inbox = config.inbox_dir() / "cr-site-reno"
    inbox.mkdir(parents=True)
    for name in ("2026-10_reno_electricity_ELB-RNO-2610.pdf", "2026-10_austin_electricity_ELB-AUS-2610-C.pdf"):
        shutil.copy(config.seed_dir() / "later" / name, inbox / name)
    with budgets.scope(conn, close["id"], "cr-collector") as b:
        batch.run_batch(conn, [inbox], workers=2)
    assert len(seen) == 2 and all(s is b for s in seen)


# --- replay ---------------------------------------------------------------------------------------------


def test_replay_reproduces_the_seed_from_the_cache_alone(model, monkeypatch, capsys):
    monkeypatch.setenv("CR_PROPOSER", "replay")
    assert main(["seed"]) == 0
    conn = db.connect()
    assert len(db.list_activities(conn)) == 10


def test_replay_never_guesses_an_uncached_document(model, monkeypatch):
    monkeypatch.setenv("CR_PROPOSER", "replay")
    main(["seed"])
    conn = db.connect()
    copy = config.inbox_dir() / "cr-site-reno" / "reno-october-resent.pdf"
    copy.parent.mkdir(parents=True)
    copy.write_bytes((config.seed_dir() / "later" / "2026-10_reno_electricity_ELB-RNO-2610.pdf").read_bytes()
                     + b"\n% re-sent\n")  # same text, new bytes: not in the cache
    result = pipeline.ingest_file(conn, copy, received_from="lena")
    assert result["status"] == "new" and result["activities"] == [] and result["proposer"] == "replay"
    assert result["gaps"] and "replay cache" in " ".join(result["notes"])
