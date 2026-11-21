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
