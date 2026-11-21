import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.browser import BrowserCalls
from qabro.journal import Journal
from qabro.recovery import Effect, reconcile


def fresh_document(browser):
    from time import monotonic_ns
    from qabro.evidence import Evidence
    return Evidence(monotonic_ns(), "document-observation", True)


class RecoveryTests(unittest.TestCase):
    def test_fresh_snapshot_confirms_submit_that_timed_out(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        records = []

        def transport(tab, tool, arguments):
            if tool == "submit":
                records.append("requirement-1")
                raise TimeoutError()
            return {"content": [{"type": "text", "text": "snapshot"}], "structuredContent": {
                "ids": records.copy(),
            }}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        with self.assertRaises(TimeoutError):
            browser.invoke("create", "submit-step", "submit", {})
        journal = Journal(journal.path)
        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        evaluate = lambda raw: (
            Effect.COMPLETED if "requirement-1" in raw["structuredContent"]["ids"] else Effect.UNKNOWN
        )
        self.assertEqual(
            reconcile(browser, "create", "inspect-create", "snapshot", {}, evaluate),
            Effect.COMPLETED,
        )
        self.assertEqual(records, ["requirement-1"])
        self.assertEqual(journal.actions_to_reconcile("attempt"), [])
        self.assertEqual(journal.events("attempt")[-1][3]["probe_event_id"], "inspect-create:finish")

    def test_runner_executes_checkpoint_after_reconciliation_without_resubmitting(self):
        from time import monotonic_ns

        from qabro.contract import Checkpoint, Scenario, Step, Verdict
        from qabro.evidence import Evidence
        from qabro.runner import Action, run_scenario

        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        calls = []

        def transport(tab, tool, arguments):
            calls.append(tool)
            if tool == "submit":
                raise TimeoutError()
            return {"content": [{"type": "text", "text": "saved"}]}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        scenario = Scenario("Submit and check", (Step("save", "Submit", (Checkpoint("saved", "Saved"),)),))

        def recover(action, step):
            reconcile(browser, action, "recovery-read", "snapshot", {}, lambda _: Effect.COMPLETED)

        def observe(check, sample):
            browser.invoke("check-read", "save", "snapshot", {}, read_only=True)
            return Evidence(monotonic_ns(), "check-read:finish", False)

        result = run_scenario(scenario, browser, lambda _: Action("submit", {}), observe, recover=recover)
        self.assertEqual(calls, ["submit", "snapshot", "snapshot"])
        self.assertEqual(result.verdict, Verdict.FAIL)

    def test_resume_interrupted_scenario_reconciles_submit_before_continuing(self):
        from qabro.contract import Scenario, Step, Verdict
        from qabro.runner import Action, run_scenario

        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "runs.sqlite"
        journal = Journal(path)
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        scenario = Scenario("Submit then close", (Step("save", "Submit"), Step("close", "Close")))
        calls = []

        def transport(tab, tool, arguments):
            calls.append(tool)
            if tool == "submit":
                raise KeyboardInterrupt()
            return {"content": [{"type": "text", "text": "saved"}]}

        def browser_for(log):
            return BrowserCalls(log, "attempt", "shared", "tab", transport, lambda value: value)

        def resolve(step):
            return Action("submit" if step.id == "save" else "close", {})

        with self.assertRaises(KeyboardInterrupt):
            run_scenario(scenario, browser_for(journal), resolve, lambda *_: None)
        reopened = browser_for(Journal(path))

        def recover(action, step):
            reconcile(reopened, action, "fresh", "snapshot", {}, lambda _: Effect.COMPLETED)

        attempt = run_scenario(scenario, reopened, resolve, lambda *_: None, recover=recover,
                               resume=True, verify_resume=fresh_document)
        self.assertEqual(calls, ["submit", "snapshot", "close"])
        self.assertEqual(attempt.verdict, Verdict.PASS)

    def test_missing_probe_cannot_confirm_completion(self):
        from qabro.recovery import confirmed_completion

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        journal.start("attempt", "run", "worker")
        browser = BrowserCalls(journal, "attempt", "shared", "tab", lambda *_: {}, lambda value: value)
        journal.append("attempt", "save:start", "tool_start", {"step": "save"})
        journal.append("attempt", "save:reconciled", "reconciliation", {
            "effect": "completed", "probe_event_id": "missing:finish",
        })
        self.assertFalse(confirmed_completion(browser, "save"))

    def test_resume_does_not_reconcile_an_action_already_observed_absent(self):
        from qabro.contract import Scenario, Step, Verdict
        from qabro.runner import Action, run_scenario

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")

        def transport(tab, tool, arguments):
            if tool == "submit":
                raise KeyboardInterrupt()
            return {"content": [{"type": "text", "text": "No matching record"}]}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        scenario = Scenario("Submit", (Step("save", "Submit"),))
        with self.assertRaises(KeyboardInterrupt):
            run_scenario(scenario, browser, lambda _: Action("submit", {}), lambda *_: None)
        self.assertIs(reconcile(browser, "step-0", "check", "snapshot", {}, lambda _: Effect.ABSENT),
                      Effect.ABSENT)
        browser.journal = Journal(path)
        result = run_scenario(
            scenario, browser, lambda _: self.fail("Must not automatically resubmit"), lambda *_: None,
            recover=lambda *_: self.fail("The effect was already reconciled"), resume=True,
            verify_resume=fresh_document,
        )
        self.assertEqual(result.verdict, Verdict.INCONCLUSIVE)
        from qabro.report import report_run

        diagnostics = report_run(browser.journal, "run")["attempts"][0]["diagnostics"]
        self.assertIn("effect_absent", [item["kind"] for item in diagnostics])
        self.assertNotIn("unresolved_effect", [item["kind"] for item in diagnostics])

    def test_resume_stops_when_fresh_observation_does_not_confirm_document(self):
        from time import monotonic_ns

        from qabro.contract import Scenario, Step
        from qabro.evidence import Evidence
        from qabro.runner import Action, EnvironmentBlocked, run_scenario

        journal = Journal(Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        scenario = Scenario("Open and save", (Step("open", "Open"), Step("save", "Save")))

        def transport(tab, tool, arguments):
            if tool == "navigate":
                return {"content": [{"type": "text", "text": "opened"}]}
            self.fail("No mutation may be sent after the document changes")

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)

        def resolve(step):
            if step.id == "save":
                raise KeyboardInterrupt()
            return Action("navigate", {})

        with self.assertRaises(KeyboardInterrupt):
            run_scenario(scenario, browser, resolve, lambda *_: None)
        with self.assertRaises(EnvironmentBlocked):
            run_scenario(
                scenario, browser, lambda _: Action("click", {}), lambda *_: None, resume=True,
                verify_resume=lambda _: Evidence(monotonic_ns(), "changed-document", False),
            )
        self.assertEqual(journal.events("attempt")[-1][3], {
            "context": "shared", "tab": "tab", "artifact_id": "changed-document", "verified": False,
        })
