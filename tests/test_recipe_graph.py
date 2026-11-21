import unittest

from qabro.contract import Step
from qabro.recipe_format import decode_recipe, encode_recipe
from qabro.runner import Recipe, RecipeCall, RecipeStep, expand_recipe


class RecipeGraphTests(unittest.TestCase):
    def test_children_are_expanded_in_order_from_exact_revisions(self):
        first = RecipeStep(Step("first", "Open"), "click", ())
        second = RecipeStep(Step("second", "Save"), "click", ())
        child = Recipe("child", "1", (second,))
        parent = Recipe("parent", "2", (first, RecipeCall("child", "1")))
        parent = decode_recipe(encode_recipe(parent))
        self.assertEqual(expand_recipe(parent, lambda *_: child, 2), (first, second))
        with self.assertRaisesRegex(ValueError, "remaining source"):
            expand_recipe(parent, lambda *_: child, 1)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            expand_recipe(parent, lambda *_: Recipe("child", "2", (second,)), 2)

    def test_cycle_fails_before_dispatch(self):
        parent = Recipe("cycle", "1", (RecipeCall("cycle", "1"),))
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            expand_recipe(parent, lambda *_: parent, 2)

    def test_argument_branches_preserve_the_source_action_and_checkpoint(self):
        from datetime import UTC, datetime

        from qabro.bindings import AttemptBindings
        from qabro.contract import Checkpoint
        from qabro.runner import ArgumentBranch

        source = Step("save", "Save", (Checkpoint("saved", "Record is saved"),))
        instruction = RecipeStep(source, "click", (), ArgumentBranch(
            "is compact", (("selector", "#compact-save"),), (("selector", "#full-save"),),
        ))
        recipe = decode_recipe(encode_recipe(Recipe("save", "1", (instruction,))))
        step, = expand_recipe(recipe, None, 1)
        self.assertEqual(step.source, source)
        bindings = AttemptBindings({}, seed=0, base_time=datetime.now(UTC))
        self.assertEqual(step.resolve(bindings, branch_value=True).arguments, {"selector": "#compact-save"})
        self.assertEqual(step.resolve(bindings, branch_value=False).arguments, {"selector": "#full-save"})
        with self.assertRaises(ValueError):
            step.resolve(bindings)
