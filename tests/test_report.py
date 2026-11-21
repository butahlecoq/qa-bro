import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns

from qabro.browser import BrowserCalls
from qabro.contract import Checkpoint, Scenario, Step, Verdict
from qabro.evidence import Evidence
from qabro.journal import Journal
from qabro.report import report_run
from qabro.runner import Action, run_scenario


class ReportTests(unittest.TestCase):
    def test_successful_retry_preserves_prior_mismatch_in_persisted_report(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        scenario = Scenario("Save", (Step("save", "Save", (Checkpoint("saved", "Saved"),)),))
        for attempt, matches in (("initial", False), ("retry", True)):
            restart = {"restart_of": "initial", "setup_artifact_id": "reset-proof"} if matches else {}
            journal.start(attempt, "run", "worker", **restart)
            journal.claim_tab("shared", attempt, attempt)
            browser = BrowserCalls(journal, attempt, "shared", attempt,
                                   lambda *_: {"content": [{"type": "text", "text": "ok"}]},
                                   lambda value: value)
            run_scenario(scenario, browser, lambda _: Action("click", {}),
                         lambda *_: Evidence(monotonic_ns(), f"snapshot-{attempt}", matches))
        report = report_run(Journal(path), "run")
        self.assertEqual(report["verdict"], Verdict.FAIL)
        self.assertTrue(report["flaky_or_recovered_after_failure"])
        self.assertEqual([row["verdict"] for row in report["attempts"]], [Verdict.FAIL, Verdict.PASS])
        self.assertEqual(report["attempts"][0]["checkpoints"][0]["artifact_id"], "snapshot-initial")
        self.assertEqual(report["attempts"][1]["restart_of"], "initial")
        self.assertEqual(report["attempts"][1]["setup_artifact_id"], "reset-proof")

        for attempt in ("initial", "retry"):
            journal.release_tab("shared", attempt, attempt)
        self.assertEqual(journal.prune(before_ns=0, max_payload_bytes=0), 0)
        pruned = report_run(Journal(path), "run")
        self.assertEqual(pruned["pruned_attempt_ids"], ["initial", "retry"])
        self.assertEqual(pruned["verdict"], Verdict.FAIL)
        self.assertEqual(pruned["attempts"], [])
        self.assertEqual(report_run(journal, "unknown")["pruned_attempt_ids"], [])

    def test_crash_after_persisted_mismatch_does_not_hide_failure(self):
        journal = Journal(Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite")
        for attempt in ("crashed", "retry"):
            journal.start(attempt, "run", "worker")
            journal.append(attempt, "scenario:start", "scenario_start", {"contract_revision": "same"})
        journal.append("crashed", "check:saved", "checkpoint", {
            "step": "save", "outcome": "observed_mismatch", "artifact_id": "first-snapshot",
        })
        journal.append("retry", "scenario:finish", "scenario_finish", {"verdict": "PASS"})
        report = report_run(Journal(journal.path), "run")
        self.assertEqual(report["verdict"], Verdict.FAIL)
        self.assertTrue(report["flaky_or_recovered_after_failure"])
        self.assertEqual(report["attempts"][0]["checkpoints"][0]["artifact_id"], "first-snapshot")
