import unittest
from dataclasses import replace

from qabro.sakai_comparison import SakaiRun, compare_sakai


class SakaiComparisonTests(unittest.TestCase):
    def test_charges_learning_and_counts_fallback_and_missing_checks(self):
        ordinary = SakaiRun(1, "matched", "PASS", ("saved",), 100, 3, 100)
        assisted = replace(ordinary, tokens=60, skill_revision="sha", skill_applied=True)
        report = compare_sakai(
            [
                (ordinary, assisted),
                (replace(ordinary, seed=2), replace(assisted, seed=2, tokens=90, skill_applied=False)),
                (replace(ordinary, seed=3), replace(assisted, seed=3, checks=(), tokens=110)),
            ],
            frozenset({"saved"}), training_tokens=20, extraction_tokens=30, validation_tokens=30,
        )
        self.assertEqual(report["both_pass"], 2)
        self.assertEqual(report["verified_reuses"], 1)
        self.assertEqual(report["estimated_reuses_to_break_even"], 2)
        self.assertEqual(report["observed_net_tokens_saved"], -40)
