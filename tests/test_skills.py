import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.budget import Budget, BudgetExhausted
from qabro.catalog import Catalog, Scope, SkillRef
from qabro.contract import Step
from qabro.skills import RunSkills


class SkillSelectionTests(unittest.TestCase):
    def test_selector_and_other_model_work_share_the_same_attempt_budget(self):
        catalog = Catalog(Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite")
        scope = Scope("fixture", "form", "requirements", "editor")
        catalog.seed_verified_hint(SkillRef("form", "1", "Fill form"), scope, "Use the named field.")
        skills = RunSkills(catalog, "run", scope, frozenset())
        budget = Budget(browser_calls=1, model_calls=1, seconds=10)
        limits = []

        def choose(step, options, remaining):
            limits.append(remaining)
            return None

        skills.select_with_model(Step("open", "Unrelated"), budget, choose)
        self.assertEqual([], limits)
        skills.select_with_model(Step("fill", "Fill"), budget, choose)
        self.assertEqual(len(limits), 1)
        self.assertGreater(limits[0], 0)
        self.assertLessEqual(limits[0], 10)
        with self.assertRaises(BudgetExhausted):
            budget.call_model(lambda _: self.fail("Limit must stop another model call"))

    def test_agent_can_load_a_selected_hint_and_decline_others(self):
        catalog = Catalog(Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite")
        scope = Scope("fixture", "form", "requirements", "editor")
        other = Scope("fixture", "form", "orders", "editor")
        ref = SkillRef("form", "1", "Fill form")
        excluded = SkillRef("other", "1", "Fill form")
        catalog.seed_verified_hint(ref, scope, "Use the name field.")
        catalog.seed_verified_hint(excluded, other, "Use the order field.")
        skills = RunSkills(catalog, "run", scope, frozenset())
        step = Step("fill", "Fill form")
        self.assertEqual(skills.select_hint(step, lambda _, refs: refs[0]), "Use the name field.")
        self.assertIsNone(skills.select_hint(step, lambda *_: None))
        with self.assertRaisesRegex(ValueError, "outside the offered scope"):
            skills.select_hint(step, lambda *_: excluded)
