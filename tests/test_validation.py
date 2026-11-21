import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Catalog, Scope, SkillRef
from qabro.contract import Attempt, Checkpoint, Observation, Scenario, Step, Verdict
from qabro.validation import HintCandidate, ValidationRun, publish_hint


class ValidationTests(unittest.TestCase):
    def test_promotion_requires_independent_evidence_and_variant_coverage(self):
        directory = self.enterContext(TemporaryDirectory())
        catalog = Catalog(Path(directory) / "catalog.sqlite")
        scope = Scope("fixture", "combobox", "requirements", "editor")
        ref = SkillRef("lookup", "1", "Search")
        candidate = HintCandidate(ref, scope, "Search at three characters.", frozenset({"below", "at"}), True)
        attempts = []
        for index, variant in enumerate(("below", "at", "at")):
            step = Step("type", "Type", (Checkpoint("threshold", f"Confirm {variant} behavior"),))
            scenario = Scenario(f"Test {variant}", (step,))
            result = Attempt(scenario, ("type",), {"threshold": Observation.MATCH})
            attempts.append(ValidationRun(ref, scope, str(index), f"setup-{index}", variant, variant, result))
        first, second, third = attempts
        self.assertFalse(publish_hint(catalog, candidate, (second, third, replace(first, session_id=second.session_id))))
        self.assertFalse(publish_hint(catalog, candidate, (first, second, replace(third, result=replace(third.result, observations={})))))
        self.assertFalse(publish_hint(catalog, candidate, tuple(replace(run, dataset_id="same") for run in attempts)))
        catalog.pin("before")
        self.assertTrue(publish_hint(catalog, candidate, tuple(attempts)))
        catalog.pin("after")
        self.assertIsNone(catalog.load_hint("before", ref))
        self.assertEqual(catalog.load_hint("after", ref), candidate.hint)

    def test_queue_publishes_only_after_validation_and_keeps_existing_pin(self):
        from datetime import UTC, datetime
        from time import monotonic_ns

        from qabro.artifacts import ArtifactStore
        from qabro.bindings import AttemptBindings
        from qabro.browser import BrowserCalls
        from qabro.evidence import Evidence
        from qabro.journal import Journal
        from qabro.runner import Action, ArgumentBranch, Recipe, RecipeStep, run_scenario
        from qabro.validation import revalidate_next_hint, validate_next_hint, validate_next_transfer
        from qabro.compatibility import propose_transfer
        from qabro.recipe_format import encode_recipe

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        catalog = Catalog(path)
        scope = Scope("fixture", "combobox", "requirements", "editor")
        draft = {
            "scope": vars(scope), "summary": "Find a category", "hint": "Open the field.",
            "variants": ["open"], "variable_inputs": False,
        }
        step = Step("open", "Open", (Checkpoint("options", "Options shown"),))
        draft["recipe"] = encode_recipe(Recipe("draft", "1", (
            RecipeStep(step, "click", (), guard="field-visible"),
        )))
        draft["capabilities"] = ["click"]
        catalog.jobs.enqueue("example", "validate_hint", draft)
        catalog.pin("before")
        store = ArtifactStore(path)
        artifacts = [store.put(f"snapshot {index}".encode(), now=1) for index in range(3)]

        guard_artifact = store.put(b"Verified visible field", now=1)

        def validate(candidate, branch_probe=None):
            step = Step("open", "Open", (Checkpoint("options", "Options shown"),))
            scenario = Scenario("Open menu", (step,))
            journal = Journal(path)
            runs = []
            for index, artifact in enumerate(artifacts):
                attempt = f"validation-{candidate.ref.id}-{candidate.ref.revision}-{index}"
                journal.start(attempt, attempt, "validator")
                journal.claim_tab("fixture", attempt, attempt)
                browser = BrowserCalls(
                    journal, attempt, "fixture", attempt,
                    lambda *_: {"content": [{"type": "text", "text": "ok"}]}, lambda value: value,
                )
                result = run_scenario(
                    scenario, browser, lambda _: Action("click", {}),
                    lambda *_: Evidence(monotonic_ns(), artifact, True),
                    choose=lambda _: candidate.recipe, applicable=lambda _: True,
                    bindings=AttemptBindings({}, seed=0, base_time=datetime.now(UTC)),
                    probe_branch=branch_probe,
                    check_recipe_guard=lambda *_: Evidence(monotonic_ns(), guard_artifact, True),
                )
                runs.append(ValidationRun(candidate.ref, candidate.scope, str(index), str(index),
                                          "fixed", "open", result, (("options", artifact),), attempt))
            return tuple(runs)

        self.assertTrue(validate_next_hint(catalog, validate, clock=lambda: 1))
        self.assertFalse(validate_next_hint(catalog, validate, clock=lambda: 2))
        catalog.pin("after")
        self.assertEqual(catalog.search("before", "category", scope, frozenset()), [])
        ref, = catalog.search("after", "category", scope, frozenset({"click"}))
        self.assertEqual(catalog.load_recipe("after", ref).id, ref.id)
        self.assertEqual(catalog.load_hint("after", ref), draft["hint"])
        store.prune(before=99, max_bytes=0)
        self.assertTrue(all(store.get(artifact) for artifact in artifacts))
        self.assertEqual(store.get(guard_artifact), b"Verified visible field")

        self.assertEqual(catalog.quarantine_scope(scope, "Changed category widget"), [ref])
        catalog.pin("during-quarantine")
        self.assertEqual(catalog.search("during-quarantine", "category", scope, frozenset()), [])
        replacement = SkillRef(ref.id, "2", ref.summary)

        def prepare(source, observed_scope):
            self.assertEqual((source, observed_scope), (ref, scope))
            step = Step("open", "Open", (Checkpoint("options", "Options shown"),))
            recipe = Recipe(replacement.id, replacement.revision, (RecipeStep(step, "click", ()),))
            return HintCandidate(replacement, scope, draft["hint"], frozenset({"open"}), False,
                                 frozenset({"click"}), recipe)

        self.assertTrue(revalidate_next_hint(catalog, prepare, validate, clock=lambda: 3))
        catalog.pin("after-revalidation")
        self.assertEqual(catalog.search("after-revalidation", "category", scope, frozenset({"click"})), [replacement])
        self.assertIsNotNone(catalog.load_recipe("after-revalidation", replacement))

        target = Scope("fixture", "combobox", "orders", "editor")
        propose_transfer(catalog, catalog.jobs, "after-revalidation", replacement, target)
        transferred = SkillRef("orders-category", "1", replacement.summary)

        def prepare_transfer(source, observed_scope, target_scope):
            self.assertEqual((source, observed_scope, target_scope), (replacement, scope, target))
            return HintCandidate(transferred, target, draft["hint"], frozenset({"open"}), False)

        self.assertTrue(validate_next_transfer(catalog, prepare_transfer, validate, clock=lambda: 4))
        catalog.pin("after-transfer")
        self.assertEqual(catalog.search("after-transfer", "category", scope, frozenset({"click"})), [replacement])
        self.assertEqual(catalog.search("after-transfer", "category", target, frozenset()), [transferred])

        fallback_recipe = Recipe("draft", "2", (
            RecipeStep(step, "click", (), ArgumentBranch(
                "compact", (("selector", "#compact"),), (("selector", "#full"),),
            )),
        ))
        draft["recipe"] = encode_recipe(fallback_recipe)
        catalog.jobs.enqueue("fallback", "validate_hint", draft)

        def validate_fallback(candidate):
            runs = validate(candidate)
            self.assertTrue(all(run.result.verdict is Verdict.PASS for run in runs))
            return runs

        self.assertTrue(validate_next_hint(catalog, validate_fallback, clock=lambda: 5))
        catalog.pin("after-fallback")
        self.assertEqual(catalog.search("after-fallback", "category", scope, frozenset({"click"})), [replacement])

        catalog.jobs.enqueue("single-branch", "validate_hint", draft)
        self.assertTrue(validate_next_hint(catalog, lambda candidate: validate(candidate, lambda *_: True),
                                          clock=lambda: 6))
        catalog.pin("after-single-branch")
        self.assertEqual(catalog.search("after-single-branch", "category", scope, frozenset({"click"})),
                         [replacement])

        catalog.jobs.enqueue("both-branches", "validate_hint", draft)
        decisions = iter((True, False, True))
        self.assertTrue(validate_next_hint(
            catalog, lambda candidate: validate(candidate, lambda *_: next(decisions)), clock=lambda: 7,
        ))
        catalog.pin("after-both-branches")
        found = catalog.search("after-both-branches", "category", scope, frozenset({"click"}))
        expected = SkillRef("hint:both-branches", "1", draft["summary"])
        self.assertCountEqual(found, [replacement, expected])
        self.assertEqual(catalog.load_recipe("after-both-branches", expected),
                         replace(fallback_recipe, id=expected.id, revision=expected.revision))

    def test_defect_trial_requires_same_observed_failure_through_recipe(self):
        from qabro.journal import Journal
        from qabro.runner import Recipe, RecipeStep
        from qabro.validation import DefectTrial, _defect_evidence

        journal = Journal(Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite")
        recipe = Recipe("candidate", "1", (RecipeStep(Step("save", "Save"), "click", ()),))
        for attempt, verdict in (("plain", Verdict.FAIL), ("replay", Verdict.FAIL), ("masked", Verdict.PASS)):
            journal.start(attempt, attempt, "validator")
            journal.append(attempt, "scenario:start", "scenario_start", {"contract_revision": "same"})
            if attempt != "plain":
                journal.append(attempt, "recipe:0", "recipe_selected", {"fingerprint": recipe.fingerprint})
                journal.append(attempt, "step-0:recipe", "recipe_action", {"action": "step-0", "fallback": False})
                journal.append(attempt, "step-0:finish", "tool_finish", {"outcome": "returned"})
            if verdict is Verdict.FAIL:
                journal.append(attempt, "check:saved", "checkpoint", {
                    "outcome": Observation.MISMATCH, "artifact_id": f"{attempt}-proof",
                })
            journal.append(attempt, "scenario:finish", "scenario_finish", {"verdict": verdict})
        self.assertEqual(
            _defect_evidence(journal, DefectTrial("plain", "replay"), recipe),
            {"plain-proof", "replay-proof"},
        )
        self.assertIsNone(_defect_evidence(journal, DefectTrial("plain", "masked"), recipe))
