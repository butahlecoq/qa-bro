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

    def test_break_even_accounts_for_maintenance_and_failed_reuse(self):
        from qabro.pilot import SkillUse, skill_break_even

        case = Case("clean", "create", Verdict.PASS)
        ordinary = Trial(case, Mode.BASELINE, "same", Verdict.PASS, 12, 100)
        reuse = Trial(case, Mode.RECIPES, "same", Verdict.PASS, 9, 40)
        uses = [SkillUse(ordinary, reuse)] * 2
        uses.append(SkillUse(ordinary, replace(reuse, verdict=Verdict.INCONCLUSIVE)))
        result = skill_break_even(uses, LearningCost(50, 10), maintenance_tokens=15)
        self.assertEqual(result["first_positive_use"], 2)
        self.assertEqual(result["investment_tokens"], 75)
        self.assertEqual(result["net_saved_tokens"], 5)
        self.assertEqual(result["incorrect_reuses"], 1)
        self.assertEqual(result["comparable_uses"], 2)

    def test_release_requires_quality_evidence_and_measurable_full_cost_savings(self):
        from qabro.pilot import ReleaseEvidence, release_report

        case = Case("defective", "create", Verdict.FAIL)
        trials = [
            Trial(case, mode, "same", Verdict.FAIL, 12, 100 if mode is Mode.BASELINE else 50)
            for mode in Mode
        ]
        learning = {Mode.HYBRID: LearningCost(10, 20)}
        proof = ReleaseEvidence(frozenset({"saved"}), frozenset({"saved"}), 0)
        evidence = {"defective": proof}
        args = (frozenset(), learning)
        self.assertTrue(release_report(trials, *args, evidence, minimum_tokens_saved=20)["ready"])
        self.assertFalse(release_report(trials, *args, evidence, minimum_tokens_saved=21)["ready"])
        self.assertFalse(release_report(trials, *args, {}, minimum_tokens_saved=20)["ready"])
        self.assertFalse(release_report(
            trials, *args, {"defective": replace(proof, duplicate_effects=1)}, minimum_tokens_saved=20,
        )["ready"])
        trials[-1] = replace(trials[-1], verdict=Verdict.PASS)
        report = release_report(trials, *args, evidence, minimum_tokens_saved=20)
        self.assertEqual(report["new_false_pass_cases"], ["defective"])
        self.assertFalse(report["ready"])
