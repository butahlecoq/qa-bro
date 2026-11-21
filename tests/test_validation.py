import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Catalog, Scope, SkillRef
from qabro.contract import Attempt, Checkpoint, Observation, Scenario, Step
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
        from qabro.validation import validate_next_hint

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        catalog = Catalog(path)
        scope = Scope("fixture", "combobox", "requirements", "editor")
        draft = {
            "scope": vars(scope), "summary": "Find a category", "hint": "Open the field.",
            "variants": ["open"], "variable_inputs": False,
        }
        catalog.jobs.enqueue("example", "validate_hint", draft)
        catalog.pin("before")

        def validate(candidate):
            step = Step("open", "Open", (Checkpoint("options", "Options shown"),))
            scenario = Scenario("Open menu", (step,))
            result = Attempt(scenario, ("open",), {"options": Observation.MATCH})
            return tuple(ValidationRun(candidate.ref, scope, str(index), str(index),
                                       "fixed", "open", result) for index in range(3))

        self.assertTrue(validate_next_hint(catalog, validate, clock=lambda: 1))
        self.assertFalse(validate_next_hint(catalog, validate, clock=lambda: 2))
        catalog.pin("after")
        self.assertEqual(catalog.search("before", "category", scope, frozenset()), [])
        ref, = catalog.search("after", "category", scope, frozenset())
        self.assertEqual(catalog.load_hint("after", ref), draft["hint"])
