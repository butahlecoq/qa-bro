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

    def test_manifest_command_writes_the_two_private_report_formats(self):
        import json
        import subprocess
        import sys
        from dataclasses import asdict
        from pathlib import Path
        from tempfile import TemporaryDirectory

        root = Path(self.enterContext(TemporaryDirectory()))
        baseline = SakaiRun(1, "matched", "PASS", ("saved",), 100, 3, 100)
        assisted = replace(baseline, tokens=75, skill_revision="sha", skill_applied=True)
        source = root / "runs.json"
        source.write_text(json.dumps({
            "pairs": [{"baseline": asdict(baseline), "assisted": asdict(assisted)}],
            "required_checks": ["saved"],
            "learning": {"training_tokens": 10, "extraction_tokens": 10, "validation_tokens": 30},
        }))
        output = root / "report"
        subprocess.run([sys.executable, "-m", "qabro.sakai_comparison", str(source), str(output)], check=True)
        report = json.loads((output / "comparison.json").read_text())
        self.assertEqual(report["estimated_reuses_to_break_even"], 2)
        self.assertIn("| 1 | PASS | PASS | yes | 100 | 75 |", (output / "report.md").read_text())
