import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns

from qabro.browser import BrowserCalls
from qabro.contract import Checkpoint, Scenario, Step, Verdict
from qabro.evidence import Evidence
from qabro.journal import Journal
from qabro.runner import Action, run_scenario


class RunnerTests(unittest.TestCase):
    def test_source_order_and_evidence_reach_the_journal(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        scenario = Scenario("Open, save, close", (
            Step("open", "Open"),
            Step("save", "Save", (Checkpoint("saved", "Record appears"),)),
            Step("close", "Close"),
        ))
        actions = []

        def transport(tab, tool, arguments):
            actions.append(arguments["label"])
            return {"content": [{"type": "text", "text": "clicked"}]}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        attempt = run_scenario(
            scenario, browser, lambda step: Action("click", {"label": step.action}),
            lambda checkpoint: Evidence(monotonic_ns(), "missing-record", False),
        )
        self.assertEqual(actions, ["Open", "Save"])
        self.assertEqual(attempt.verdict, Verdict.FAIL)
        checks = [payload for _, _, kind, payload in journal.events("attempt") if kind == "checkpoint"]
        self.assertEqual(checks, [{
            "step": "save", "outcome": "observed_mismatch", "artifact_id": "missing-record",
        }])
