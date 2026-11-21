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
            lambda checkpoint, sample: Evidence(monotonic_ns(), "missing-record", False),
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
            lambda check, sample: Evidence(monotonic_ns(), "wrong-name", False),
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
            scenario, browser, lambda step: Action("click", {}), lambda check, sample: None,
        )
        self.assertEqual(calls, ["snapshot", "click"])
        self.assertEqual(attempt.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(attempt.completed_steps, ("open",))
        self.assertIn("budget_exhausted", [entry[2] for entry in journal.events("attempt")])

    def test_budget_exhaustion_during_check_keeps_explicit_condition_results(self):
        from qabro.budget import Budget

        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        scenario = Scenario("Save, then close", (
            Step("save", "Save", (Checkpoint("saved", "Saved"),)),
            Step("close", "Close", (Checkpoint("closed", "Closed"),)),
        ))
        browser = BrowserCalls(
            journal, "attempt", "shared", "tab",
            lambda *_: {"content": [{"type": "text", "text": "returned"}]},
            lambda value: value, budget=Budget(browser_calls=1, model_calls=0, seconds=10),
        )

        def observe(checkpoint, sample):
            browser.invoke("inspect", "save", "snapshot", {}, read_only=True)

        attempt = run_scenario(scenario, browser, lambda _: Action("click", {}), observe)
        self.assertEqual(attempt.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(attempt.observations, {"saved": "unverified", "closed": "not_reached"})
        self.assertEqual(journal.events("attempt")[-1][3]["verdict"], "INCONCLUSIVE")

    def test_eventual_checkpoint_journals_each_sample_under_a_unique_id(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        scenario = Scenario("Save", (
            Step("save", "Save", (Checkpoint("saved", "Saved", wait_ns=1_000_000_000),)),
        ))
        browser = BrowserCalls(
            journal, "attempt", "shared", "tab",
            lambda *_: {"content": [{"type": "text", "text": "returned"}]},
            lambda value: value,
        )

        def observe(checkpoint, sample):
            event = f"{checkpoint.id}:sample:{sample}"
            browser.invoke(event, "save", "snapshot", {}, read_only=True)
            return Evidence(monotonic_ns(), f"snapshot-{sample}", sample == 1)

        attempt = run_scenario(scenario, browser, lambda _: Action("click", {}), observe)
        self.assertEqual(attempt.verdict, Verdict.PASS)
        events = [event for _, event, kind, _ in journal.events("attempt") if kind == "tool_start"]
        self.assertEqual(events, ["step-0:start", "saved:sample:0:start", "saved:sample:1:start"])

    def test_resume_loads_the_pinned_recipe_for_remaining_steps(self):
        from datetime import UTC, datetime

        from qabro.bindings import AttemptBindings
        from qabro.runner import Recipe, RecipeStep

        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        first, second = Step("first", "Open"), Step("second", "Save")
        scenario = Scenario("Open and save", (first, second))
        recipe = Recipe("form", "1", (RecipeStep(first, "open", ()), RecipeStep(second, "save", ())))
        browser = BrowserCalls(journal, "attempt", "shared", "tab",
                               lambda *_: {"content": [{"type": "text", "text": "ok"}]},
                               lambda value: value)
        bindings = AttemptBindings({}, seed=1, base_time=datetime.now(UTC))
        append = journal.append

        def interrupt(attempt, event, *args, **kwargs):
            if event == "step-1:window":
                raise KeyboardInterrupt()
            return append(attempt, event, *args, **kwargs)

        journal.append = interrupt
        with self.assertRaises(KeyboardInterrupt):
            run_scenario(scenario, browser, lambda _: self.fail(), lambda *_: None,
                         choose=lambda _: recipe, applicable=lambda _: True, bindings=bindings)
        browser.journal = Journal(journal.path)
        with self.assertRaisesRegex(ValueError, "pinned recipe"):
            run_scenario(scenario, browser, lambda _: self.fail(), lambda *_: None,
                         bindings=bindings, resume=True)
        result = run_scenario(scenario, browser, lambda _: self.fail(), lambda *_: None,
                              bindings=bindings, resume=True, load_recipe=lambda *_: recipe)
        self.assertEqual(result.verdict, Verdict.PASS)

    def test_uncertain_effect_is_reported_with_the_action_reference(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        scenario = Scenario("Save", (Step("save", "Save"),))
        browser = BrowserCalls(journal, "attempt", "shared", "tab", lambda *_: {},
                               lambda value: value)
        attempt = run_scenario(scenario, browser, lambda _: Action("click", {}), lambda *_: None)
        self.assertEqual(attempt.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(journal.events("attempt")[-2][3], {
            "step": "save", "action_event_id": "step-0:start",
        })
        self.assertEqual(journal.events("attempt")[-1][3], {
            "verdict": "INCONCLUSIVE", "cause": "unknown",
        })

    def test_ambiguous_target_stops_before_dispatch_and_preserves_evidence(self):
        from qabro.runner import AmbiguousTarget

        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        scenario = Scenario("Click Save", (Step("save", "Click Save"),))
        browser = BrowserCalls(journal, "attempt", "shared", "tab",
                               lambda *_: self.fail("Ambiguous target must not be clicked"),
                               lambda value: value)

        def resolve(step):
            raise AmbiguousTarget("snapshot-with-two-buttons")

        attempt = run_scenario(scenario, browser, resolve, lambda *_: None)
        self.assertEqual(attempt.verdict, Verdict.INCONCLUSIVE)
        events = {kind: payload for _, _, kind, payload in journal.events("attempt")}
        self.assertNotIn("tool_start", events)
        self.assertEqual(events["ambiguous_target"], {
            "step": "save", "artifact_id": "snapshot-with-two-buttons",
        })
        self.assertEqual(events["scenario_finish"]["cause"], "automation")

    def test_environment_block_preserves_evidence_and_verdict(self):
        from qabro.runner import EnvironmentBlocked

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        journal.start("attempt", "run", "worker")
        scenario = Scenario("Open application", (Step("open", "Open application"),))
        browser = BrowserCalls(journal, "attempt", "shared", "tab",
                               lambda *_: self.fail("Blocked scenario must not dispatch"),
                               lambda value: value)

        def resolve(step):
            raise EnvironmentBlocked("expired-session")

        result = run_scenario(scenario, browser, resolve, lambda *_: None)
        self.assertEqual(result.verdict, Verdict.BLOCKED)
        self.assertEqual(journal.events("attempt")[-2][3], {
            "step": "open", "artifact_id": "expired-session",
        })
        self.assertEqual(journal.events("attempt")[-1][3], {
            "cause": "environment", "verdict": "BLOCKED",
        })

    def test_catalog_recipe_falls_back_when_its_precondition_fails(self):
        from datetime import UTC, datetime

        from qabro.bindings import AttemptBindings
        from qabro.catalog import Catalog, Scope, SkillRef
        from qabro.runner import Recipe, RecipeStep
        from qabro.skills import RunSkills

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, catalog = Journal(path), Catalog(path)
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        step = Step("save", "Save requirements")
        scope = Scope("fixture", "form", "requirements", "editor")
        ref = SkillRef("save", "1", "Save requirements")
        recipe = Recipe(ref.id, ref.revision, (RecipeStep(step, "recipe-click", ()),))
        catalog.seed_verified_hint(ref, scope, "Save the form", recipe=recipe)
        skills = RunSkills(catalog, "run", scope, frozenset())
        called = []

        def transport(tab, tool, arguments):
            called.append(tool)
            return {"content": [{"type": "text", "text": "ok"}]}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        result = run_scenario(
            Scenario(step.action, (step,)), browser, lambda _: Action("ordinary-click", {}),
            lambda *_: None,
            choose=lambda source: skills.select_recipe(source, lambda _, options: options[0]),
            applicable=lambda selected: False,
            bindings=AttemptBindings({}, seed=1, base_time=datetime.now(UTC)),
        )
        self.assertEqual(called, ["ordinary-click"])
        self.assertEqual(result.verdict, Verdict.PASS)
