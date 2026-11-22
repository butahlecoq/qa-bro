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
        baseline = SakaiRun(1, "matched", "PASS", ("saved",), 100, 3, 2_000_000_000, mcp_calls=6, worker_tool_calls=8)
        assisted = replace(baseline, tokens=75, skill_revision="sha", skill_applied=True, mcp_calls=4, worker_tool_calls=5)
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
        self.assertIn("| Worker tool calls | 8 | 5 | 3 |", (output / "report.md").read_text())
        self.assertIn("| MCP calls | 6 | 4 | 2 |", (output / "report.md").read_text())
        self.assertIn("| Browser actions | — | — | — |", (output / "report.md").read_text())

    def test_measurement_alternates_order_and_keeps_each_pair_on_one_seed(self):
        import json
        from hashlib import sha256
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from qabro.sakai_comparison import measure_sakai

        directory = Path(self.enterContext(TemporaryDirectory()))
        content = b"Verified skill."
        digest = sha256(content).hexdigest()
        (directory / "SKILL.md").write_bytes(content)
        (directory / "manifest.json").write_text(json.dumps({"status": "active", "content_sha256": digest}))
        calls = []

        def worker(seed, skill):
            calls.append((seed, skill is not None))
            return SakaiRun(seed, "matched", "PASS", ("saved",), 10, 1, 100,
                            digest if skill else None, skill is not None)

        pairs = measure_sakai(directory, (4, 5), frozenset({1, 2, 3}), worker)
        self.assertEqual(calls, [(4, False), (4, True), (5, True), (5, False)])
        self.assertEqual([baseline.seed for baseline, _ in pairs], [4, 5])
        with self.assertRaisesRegex(ValueError, "training and validation seeds"):
            measure_sakai(directory, (3,), frozenset({1, 2, 3}), worker)

    def test_worker_export_keeps_costs_when_a_passing_verdict_lacks_evidence(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from qabro.journal import Journal
        from qabro.sakai_comparison import measured_worker_run

        path = Path(self.enterContext(TemporaryDirectory())) / "attempt.sqlite"
        journal = Journal(path)
        journal.start("run", "series", "worker")
        journal.append("run", "sakai:worker", "worker_metadata", {
            "seed": 4, "model": "fixture", "target_url": "http://127.0.0.1:5173/pages/crud",
            "budgets": {"model_calls": 10}, "browser_schema_sha256": "schema", "scenario_sha256": "scenario",
        })
        journal.append("run", "sakai:usage", "worker_usage", {
            "tokens": 200, "model_calls": 3, "elapsed_ns": 10, "mcp_calls": 4, "browser_actions": 7,
        })
        journal.append("run", "scenario:finish", "scenario_finish", {"case": "SAKAI-02", "verdict": "PASS"})
        result = measured_worker_run(path, "run")
        self.assertEqual((result.verdict, result.tokens, result.mcp_calls, result.browser_actions),
                         ("INCONCLUSIVE", 200, 4, 7))
