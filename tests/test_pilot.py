import unittest
from dataclasses import replace

from qabro.contract import Verdict
from qabro.pilot import Case, LearningCost, Mode, Trial, Usage, frozen_catalog_report


class PilotTests(unittest.TestCase):
    def test_reports_quality_and_full_cost_for_matched_held_out_cases(self):
        clean = Case("clean", "create", Verdict.PASS)
        defect = Case("defect", "create", Verdict.FAIL)
        trials = [
            Trial(case, mode, "same model and budget", case.expected, 12, 100, Usage(2, 70, 30, 3, 9))
            for mode in Mode for case in (clean, defect)
        ]
        trials[-1] = replace(trials[-1], verdict=Verdict.PASS, elapsed_ns=18)
        report = frozen_catalog_report(trials, frozenset({"edit"}), {
            Mode.HYBRID: LearningCost(10, 20, Usage(1, 8, 2, 1, 3), Usage(2, 16, 4, 5, 12)),
        })
        self.assertEqual(report[Mode.HYBRID]["usage"]["total"], {
            "model_calls": 7, "input_tokens": 164, "output_tokens": 66,
            "browser_calls": 12, "browser_ns": 33,
        })
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

    def test_online_report_records_catalog_changes_and_final_learning_cost(self):
        from qabro.pilot import OnlineAttempt, online_learning_report

        case = Case("clean", "create", Verdict.PASS)
        trial = Trial(case, Mode.HYBRID, "same", Verdict.PASS, 12, 100)
        first = OnlineAttempt("a", trial, (), LearningCost(8, 2))
        second = OnlineAttempt("b", trial, (("choose-category", "1"),), LearningCost(3, 7))
        report = online_learning_report([first, second], final_learning=LearningCost(1, 4))
        self.assertEqual([row["available_revisions"] for row in report["attempts"]], [
            [], [["choose-category", "1"]],
        ])
        self.assertEqual([row["cumulative_tokens"] for row in report["attempts"]], [110, 220])
        self.assertEqual(report["total_tokens"], 225)
        with self.assertRaises(ValueError):
            online_learning_report([first, first])

    def test_pilot_command_reads_a_frozen_export(self):
        import json
        import subprocess
        import sys
        from dataclasses import asdict
        from pathlib import Path
        from tempfile import TemporaryDirectory

        case = Case("defect", "create", Verdict.FAIL)
        trials = [
            Trial(case, mode, "same", Verdict.FAIL, 100, 10 if mode is Mode.RECIPES else 20)
            for mode in Mode
        ]
        directory = Path(self.enterContext(TemporaryDirectory()))
        manifest = directory / "pilot.json"
        transfer_case = Case("transfer-defect", "transfer-create", Verdict.FAIL)
        transfer_trials = [
            replace(trial, case=transfer_case, verdict=Verdict.PASS if trial.mode is Mode.HYBRID else Verdict.FAIL)
            for trial in trials
        ]
        manifest.write_text(json.dumps({
            "kind": "frozen", "platform": "fixture-a", "trials": [asdict(trial) for trial in trials],
            "transfer": {
                "platform": "fixture-b", "trials": [asdict(trial) for trial in transfer_trials], "learning": {},
            },
            "training_workflows": ["edit"], "learning": {},
            "skills": {"create:1": {
                "uses": [{"case_id": "defect", "mode": "recipes"}],
                "learning": {"explorer_tokens": 2, "validation_tokens": 3},
                "maintenance_tokens": 1,
            }},
            "release": {
                "minimum_tokens_saved": 1,
                "evidence": {"defect": {
                    "mandatory_condition_ids": ["saved"], "reported_condition_ids": ["saved"],
                    "duplicate_effects": 0,
                }},
            },
        }))
        result = subprocess.run(
            [sys.executable, "-m", "qabro.pilot", str(manifest)],
            check=True, text=True, capture_output=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["modes"]["hybrid"]["detected_defects"], 1)
        self.assertFalse(report["release"]["ready"])
        self.assertEqual(report["transfer"]["target_platform"], "fixture-b")
        self.assertEqual(report["transfer"]["modes"]["hybrid"]["false_pass"], 1)
        self.assertEqual(report["modes"]["hybrid"]["false_pass"], 0)
        self.assertEqual(report["skill_break_even"]["create:1"]["first_positive_use"], 1)
        self.assertEqual(report["skill_break_even"]["create:1"]["net_saved_tokens"], 4)
