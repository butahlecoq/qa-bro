import unittest
from dataclasses import replace

from qabro.contract import Verdict
from qabro.pilot import Case, LearningCost, Mode, Trial, frozen_catalog_report


class PilotTests(unittest.TestCase):
    def test_reports_quality_and_full_cost_for_matched_held_out_cases(self):
        clean = Case("clean", "create", Verdict.PASS)
        defect = Case("defect", "create", Verdict.FAIL)
        trials = [
            Trial(case, mode, "same model and budget", case.expected, 12, 100)
            for mode in Mode for case in (clean, defect)
        ]
        trials[-1] = replace(trials[-1], verdict=Verdict.PASS, elapsed_ns=18)
        report = frozen_catalog_report(trials, frozenset({"edit"}), {Mode.HYBRID: LearningCost(10, 20)})
        self.assertEqual(report[Mode.HYBRID]["false_pass"], 1)
        self.assertEqual(report[Mode.HYBRID]["detected_defects"], 0)
        self.assertEqual(report[Mode.HYBRID]["p95_ns"], 18)
        self.assertEqual(report[Mode.HYBRID]["total_tokens"], 230)
        self.assertEqual(report[Mode.BASELINE]["detected_defects"], 1)
        with self.assertRaises(ValueError):
            frozen_catalog_report(trials, frozenset({"create"}), {})
        with self.assertRaises(ValueError):
            frozen_catalog_report(trials[:-1], frozenset(), {})
