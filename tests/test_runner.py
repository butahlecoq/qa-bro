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

    def test_selected_recipe_preserves_intermediate_checkpoint(self):
        from datetime import UTC, datetime

        from qabro.bindings import AttemptBindings, Literal
        from qabro.runner import Parameter, Recipe, RecipeStep

        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        fill = Step("fill", "Fill name", (Checkpoint("name", "Name is shown"),))
        save = Step("save", "Save")
        scenario = Scenario("Fill name and save", (fill, save))
        recipe = Recipe("form", "1", (
            RecipeStep(fill, "type", (("text", Parameter("name")),)),
            RecipeStep(save, "click", (("label", "Save"),)),
        ))
        calls = []

        def transport(tab, tool, arguments):
            calls.append((tool, arguments))
            return {"content": [{"type": "text", "text": "returned"}]}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        bindings = AttemptBindings({"name": Literal("Example")}, seed=1, base_time=datetime.now(UTC))
        attempt = run_scenario(
            scenario, browser, lambda step: self.fail("Expected selected recipe"),
            lambda check: Evidence(monotonic_ns(), "wrong-name", False),
            choose=lambda step: recipe, applicable=lambda recipe: True, bindings=bindings,
        )
        self.assertEqual(calls, [("type", {"text": "Example"})])
        self.assertEqual(attempt.verdict, Verdict.FAIL)
        self.assertIn("recipe_selected", [entry[2] for entry in journal.events("attempt")])

    def test_browser_budget_applies_across_dispatchers_and_stops_scenario(self):
        from qabro.budget import Budget

        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        calls = []

        def transport(tab, tool, arguments):
            calls.append(tool)
            return {"content": [{"type": "text", "text": "returned"}]}

        budget = Budget(browser_calls=2, model_calls=1, seconds=10)
        args = (journal, "attempt", "shared", "tab", transport, lambda value: value)
        helper = BrowserCalls(*args, budget=budget)
        helper.invoke("initial", "open", "snapshot", {})
        browser = BrowserCalls(*args, budget=budget)
        scenario = Scenario("Open, save", (Step("open", "Open"), Step("save", "Save")))
        attempt = run_scenario(
            scenario, browser, lambda step: Action("click", {}), lambda check: None,
        )
        self.assertEqual(calls, ["snapshot", "click"])
        self.assertEqual(attempt.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(attempt.completed_steps, ("open",))
        self.assertIn("budget_exhausted", [entry[2] for entry in journal.events("attempt")])
