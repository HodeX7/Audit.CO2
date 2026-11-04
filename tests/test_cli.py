"""End-to-end CLI tests: runs the actual `carbonroom` commands as
subprocesses, the same way a person typing them would, against a fresh
temp database each time. This is the test that would have caught the
CSV-quoting bug and the float-vs-Decimal bug from our live dry run --
the per-function unit tests above did not exercise the real SQLite layer.

Run with: python3 -m unittest tests.test_cli -v
"""

import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

REPO = pathlib.Path(__file__).resolve().parent.parent


def run_cli(db_path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "carbonroom.cli", "--db", db_path, *args],
        cwd=REPO, capture_output=True, text=True,
    )


class TestCliEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = str(pathlib.Path(self.tmp_dir) / "test.db")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

    def _gaps(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM gaps")]
        conn.close()
        return rows

    def test_seed_calc_check_finds_all_five_demo_traps(self):
        self.assertEqual(run_cli(self.db_path, "seed-demo").returncode, 0)
        calc_result = run_cli(self.db_path, "calc", "--period", "2026-10")
        self.assertEqual(calc_result.returncode, 0, calc_result.stderr)
        self.assertIn("Calculated", calc_result.stdout)

        check_result = run_cli(self.db_path, "check", "--period", "2026-10")
        self.assertEqual(check_result.returncode, 0, check_result.stderr)
        gaps = self._gaps()
        kinds = {g["kind"] for g in gaps}
        self.assertEqual(
            kinds,
            {"missing_doc", "conflict", "stale_factor", "outlier", "excerpt_mismatch"},
        )

    def test_check_is_idempotent_through_the_cli(self):
        run_cli(self.db_path, "seed-demo")
        run_cli(self.db_path, "calc", "--period", "2026-10")
        run_cli(self.db_path, "check", "--period", "2026-10")
        n_gaps_first = len(self._gaps())

        second = run_cli(self.db_path, "check", "--period", "2026-10")
        self.assertIn("0 new gap(s)", second.stdout)
        self.assertEqual(len(self._gaps()), n_gaps_first)

    def test_publish_refused_without_approval_then_succeeds_after(self):
        run_cli(self.db_path, "seed-demo")
        run_cli(self.db_path, "calc", "--period", "2026-10")
        run_cli(self.db_path, "check", "--period", "2026-10")

        refused = run_cli(self.db_path, "report", "--period", "2026-10", "--publish")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("REFUSED", refused.stdout)

        approved = run_cli(self.db_path, "approve", "--period", "2026-10", "--by", "grace")
        self.assertEqual(approved.returncode, 0)

        published = run_cli(self.db_path, "report", "--period", "2026-10", "--publish")
        self.assertEqual(published.returncode, 0, published.stderr)
        self.assertIn("PUBLISHED", published.stdout)

        conn = sqlite3.connect(self.db_path)
        period = conn.execute("SELECT status FROM periods WHERE id = '2026-10'").fetchone()
        conn.close()
        self.assertEqual(period[0], "CLOSED")

    def test_full_resolution_flow_reaches_a_sane_coverage(self):
        run_cli(self.db_path, "seed-demo")
        run_cli(self.db_path, "calc", "--period", "2026-10")
        run_cli(self.db_path, "check", "--period", "2026-10")
        gaps_by_kind = {g["kind"]: g["id"] for g in self._gaps()}

        run_cli(self.db_path, "resolve", gaps_by_kind["conflict"], "--answer", "use act-diesel-2", "--by", "omar")
        run_cli(self.db_path, "resolve", gaps_by_kind["stale_factor"], "--answer", "approve", "--by", "grace")
        run_cli(self.db_path, "resolve", gaps_by_kind["excerpt_mismatch"],
                "--answer", "exclude: corrected bill supersedes this", "--by", "omar")
        run_cli(self.db_path, "resolve", gaps_by_kind["outlier"], "--answer", "accept: known spike", "--by", "maya")

        run_cli(self.db_path, "calc", "--period", "2026-10")
        check2 = run_cli(self.db_path, "check", "--period", "2026-10")
        self.assertIn("0 new gap(s)", check2.stdout)

        run_cli(self.db_path, "approve", "--period", "2026-10", "--by", "grace")
        out_path = pathlib.Path(self.tmp_dir) / "report.json"
        published = run_cli(self.db_path, "report", "--period", "2026-10", "--publish", "--out", str(out_path))
        self.assertEqual(published.returncode, 0, published.stderr)

        report = json.loads(out_path.read_text())
        self.assertEqual(report["status"], "PUBLISHED")
        # Reno's missing bill is the one gap nobody can resolve without a
        # real document, so it's the only thing still keeping coverage < 100%.
        open_gaps = [g for g in report["gaps"] if g["status"] == "OPEN"]
        self.assertEqual(len(open_gaps), 1)
        self.assertEqual(open_gaps[0]["kind"], "missing_doc")
        self.assertGreater(report["coverage_pct"], 0)
        self.assertLess(report["coverage_pct"], 100)

    def test_ask_names_the_gap_owner_for_missing_data(self):
        run_cli(self.db_path, "seed-demo")
        run_cli(self.db_path, "calc", "--period", "2026-10")
        run_cli(self.db_path, "check", "--period", "2026-10")
        result = run_cli(self.db_path, "ask", "what is the reno electricity total", "--period", "2026-10")
        self.assertIn("UNKNOWN", result.stdout)
        self.assertIn("@lena", result.stdout)

    def test_calc_skips_already_verified_but_force_overrides(self):
        run_cli(self.db_path, "seed-demo")
        first = run_cli(self.db_path, "calc", "--period", "2026-10")
        self.assertIn("already-settled VERIFIED activities skipped", first.stdout)

        forced = run_cli(self.db_path, "calc", "--period", "2026-10", "--force")
        self.assertNotIn("skipped", forced.stdout)


class TestResolveNluFallback(unittest.TestCase):
    """Drives `resolve` through the real CLI (in-process, so we can mock
    the LLM boundary) to prove the fallback wiring itself works -- not
    just the isolated nlu.py module tested in test_nlu.py."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = str(pathlib.Path(self.tmp_dir) / "test.db")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        run_cli(self.db_path, "seed-demo")
        run_cli(self.db_path, "calc", "--period", "2026-10")
        check = run_cli(self.db_path, "check", "--period", "2026-10")
        self.assertEqual(check.returncode, 0, check.stderr)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self.conflict_gap_id = conn.execute(
            "SELECT id FROM gaps WHERE kind = 'conflict'"
        ).fetchone()["id"]
        conn.close()

    def test_without_llm_configured_loose_phrase_is_refused_not_guessed(self):
        from carbonroom import cli

        with mock.patch("carbonroom.llm.is_configured", return_value=False):
            rc = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                            "--answer", "yeah go with the second one", "--by", "omar"])
        self.assertEqual(rc, 1)

    def _gap_and_activities(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        gap = dict(conn.execute("SELECT * FROM gaps WHERE id = ?", (self.conflict_gap_id,)).fetchone())
        act1 = dict(conn.execute("SELECT * FROM activities WHERE id = 'act-diesel-1'").fetchone())
        act2 = dict(conn.execute("SELECT * FROM activities WHERE id = 'act-diesel-2'").fetchone())
        conn.close()
        return gap, act1, act2

    def test_translated_resolution_is_proposed_not_applied_until_confirmed(self):
        from carbonroom import cli

        with mock.patch("carbonroom.llm.is_configured", return_value=True), \
             mock.patch("carbonroom.llm.complete", return_value="use act-diesel-2"):
            rc = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                            "--answer", "yeah go with the second one", "--by", "omar"])
        self.assertEqual(rc, 0)

        # Nothing applied yet -- this is the core safety fix. (Both
        # activities are CONFLICTING, not UNVERIFIED, because `check` in
        # setUp already flagged the conflict -- that's the baseline.)
        gap, act1, act2 = self._gap_and_activities()
        self.assertEqual(gap["status"], "OPEN")
        self.assertEqual(act1["status"], "CONFLICTING")
        self.assertEqual(act2["status"], "CONFLICTING")

    def test_confirming_a_pending_translation_applies_it(self):
        from carbonroom import cli

        with mock.patch("carbonroom.llm.is_configured", return_value=True), \
             mock.patch("carbonroom.llm.complete", return_value="use act-diesel-2"):
            cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                      "--answer", "yeah go with the second one", "--by", "omar"])

        rc = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id, "--answer", "yes", "--by", "omar"])
        self.assertEqual(rc, 0)

        gap, act1, act2 = self._gap_and_activities()
        self.assertEqual(gap["status"], "RESOLVED")
        self.assertEqual(act2["status"], "UNVERIFIED")  # sent back for re-verification
        self.assertEqual(act1["status"], "EXCLUDED")    # the one not chosen

    def test_cancelling_a_pending_translation_applies_nothing(self):
        from carbonroom import cli

        with mock.patch("carbonroom.llm.is_configured", return_value=True), \
             mock.patch("carbonroom.llm.complete", return_value="use act-diesel-2"):
            cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                      "--answer", "yeah go with the second one", "--by", "omar"])

        rc = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id, "--answer", "no", "--by", "omar"])
        self.assertEqual(rc, 0)

        gap, act1, act2 = self._gap_and_activities()
        self.assertEqual(gap["status"], "OPEN")
        self.assertEqual(act1["status"], "CONFLICTING")
        self.assertEqual(act2["status"], "CONFLICTING")

        # And the cancelled pending doesn't linger: a nonsense phrase (not
        # "yes" -- that's its own valid exact command in resolve.py,
        # unrelated to pending-confirmation) with no pending left to
        # confirm is just an unrecognized reply.
        with mock.patch("carbonroom.llm.is_configured", return_value=False):
            rc2 = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                             "--answer", "asdkjf not a real command", "--by", "omar"])
        self.assertEqual(rc2, 1)
        gap2, _, _ = self._gap_and_activities()
        self.assertEqual(gap2["status"], "OPEN")

    def test_a_fresh_exact_reply_supersedes_a_stale_pending_translation(self):
        from carbonroom import cli

        with mock.patch("carbonroom.llm.is_configured", return_value=True), \
             mock.patch("carbonroom.llm.complete", return_value="use act-diesel-2"):
            cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                      "--answer", "yeah go with the second one", "--by", "omar"])

        # Instead of confirming, the human just gives the exact command directly
        # (e.g. changed their mind) -- this should apply immediately, not get
        # swallowed as a non-confirmation of the old pending translation.
        rc = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                        "--answer", "use act-diesel-1", "--by", "omar"])
        self.assertEqual(rc, 0)

        gap, act1, act2 = self._gap_and_activities()
        self.assertEqual(gap["status"], "RESOLVED")
        self.assertEqual(act1["status"], "UNVERIFIED")
        self.assertEqual(act2["status"], "EXCLUDED")

        # And the superseded pending is gone -- a nonsense follow-up isn't
        # treated as confirming it (there's nothing left to confirm).
        with mock.patch("carbonroom.llm.is_configured", return_value=False):
            rc2 = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                             "--answer", "asdkjf not a real command", "--by", "omar"])
        self.assertEqual(rc2, 1)

    def test_model_hallucinating_a_wrong_id_is_still_refused(self):
        from carbonroom import cli

        with mock.patch("carbonroom.llm.is_configured", return_value=True), \
             mock.patch("carbonroom.llm.complete", return_value="use act-totally-made-up"):
            rc = cli.main(["--db", self.db_path, "resolve", self.conflict_gap_id,
                            "--answer", "the usual one I guess", "--by", "omar"])
        self.assertEqual(rc, 1)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        gap = dict(conn.execute("SELECT * FROM gaps WHERE id = ?", (self.conflict_gap_id,)).fetchone())
        conn.close()
        self.assertEqual(gap["status"], "OPEN")  # untouched -- refused, not guessed


if __name__ == "__main__":
    unittest.main()
