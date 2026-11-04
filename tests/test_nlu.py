"""Tests for carbonroom/check/nlu.py. Every test injects a FAKE llm_call
(a plain Python function) instead of calling a real model -- zero network
calls, zero API key needed, and the behavior is fully deterministic. This
is the point: the translation logic (prompting, parsing, validating) is
testable on its own, independent of which real model ends up behind it.

Run with: python3 -m unittest tests.test_nlu -v
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from carbonroom.check import CandidateActivity, NeedsClarificationError, translate_reply

GAP = {"id": "gap-1", "kind": "conflict", "detail": "2 diesel invoices disagree for austin 2026-10"}
CANDIDATES = [
    CandidateActivity("act-diesel-1", "500 gallon, doc-diesel-1"),
    CandidateActivity("act-diesel-2", "550 gallon, doc-diesel-2"),
]


def _fake_llm(fixed_response: str):
    """Returns a stub llm_call that ignores the prompt and always answers
    with `fixed_response` -- used to test translate_reply's parsing and
    validation without any real model."""
    return lambda prompt: fixed_response


class TestTranslateReplyHappyPaths(unittest.TestCase):
    def test_natural_phrase_mapped_to_use_second_candidate(self):
        # Simulates a model correctly reading "go with the second one" and
        # mapping it to the id at position 2 in the candidate list.
        result = translate_reply(GAP, CANDIDATES, "yeah go with the second one",
                                  llm_call=_fake_llm("use act-diesel-2"))
        self.assertEqual(result, "use act-diesel-2")

    def test_natural_phrase_mapped_to_exclude(self):
        result = translate_reply(GAP, CANDIDATES, "drop the first one, it's a dupe",
                                  llm_call=_fake_llm("exclude: duplicate invoice"))
        self.assertEqual(result, "exclude: duplicate invoice")

    def test_natural_phrase_mapped_to_accept(self):
        result = translate_reply(GAP, CANDIDATES, "yeah that's fine, we know about it",
                                  llm_call=_fake_llm("accept: known issue"))
        self.assertEqual(result, "accept: known issue")

    def test_natural_phrase_mapped_to_approve(self):
        result = translate_reply(GAP, CANDIDATES, "looks good, go ahead",
                                  llm_call=_fake_llm("approve"))
        self.assertEqual(result, "approve")

    def test_numeric_passthrough(self):
        result = translate_reply(GAP, CANDIDATES, "number 2 please", llm_call=_fake_llm("2"))
        self.assertEqual(result, "2")


class TestTranslateReplyRefusesRatherThanGuesses(unittest.TestCase):
    def test_explicit_unclear_raises(self):
        with self.assertRaises(NeedsClarificationError):
            translate_reply(GAP, CANDIDATES, "hmm not sure, what do you think?",
                             llm_call=_fake_llm("UNCLEAR"))

    def test_model_output_off_menu_is_rejected_not_passed_through(self):
        # The model ignored instructions and wrote a sentence instead of
        # one of the fixed formats -- must be refused, not forwarded.
        with self.assertRaises(NeedsClarificationError):
            translate_reply(GAP, CANDIDATES, "go with the second one",
                             llm_call=_fake_llm("I think you should use the second invoice."))

    def test_model_inventing_an_activity_id_not_in_candidates_is_rejected(self):
        # Defense in depth: even if the model hallucinates a plausible-looking
        # id, this module itself (not just resolve_gap downstream) refuses it.
        with self.assertRaises(NeedsClarificationError):
            translate_reply(GAP, CANDIDATES, "use the usual one",
                             llm_call=_fake_llm("use act-diesel-99"))

    def test_empty_candidate_list_still_allows_accept_and_approve(self):
        result = translate_reply(
            {"id": "gap-2", "kind": "outlier", "detail": "austin gas +60%"},
            [], "yeah that's a known seasonal thing",
            llm_call=_fake_llm("accept: seasonal heater usage"),
        )
        self.assertEqual(result, "accept: seasonal heater usage")


class TestPromptNeverLeaksOutsideInstructions(unittest.TestCase):
    def test_prompt_includes_the_verbatim_reply_and_candidate_ids(self):
        captured = {}

        def capturing_llm(prompt: str) -> str:
            captured["prompt"] = prompt
            return "use act-diesel-2"

        translate_reply(GAP, CANDIDATES, "go with the second one", llm_call=capturing_llm)
        self.assertIn("go with the second one", captured["prompt"])
        self.assertIn("act-diesel-1", captured["prompt"])
        self.assertIn("act-diesel-2", captured["prompt"])
        self.assertIn("UNCLEAR", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
