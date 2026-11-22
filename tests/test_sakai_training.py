import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.artifacts import ArtifactStore
from qabro.journal import Journal
from qabro.sakai_cases import CREATE_CHECKS
from qabro.sakai_training import training_summary


class SakaiTrainingTests(unittest.TestCase):
    def test_passing_verdict_without_a_stored_checkpoint_is_insufficient(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "training.sqlite"
        journal, store = Journal(path), ArtifactStore(path)
        journal.start("training", "series", "worker")
        proof = store.put(b"evidence fixture", now=1)
        for step in CREATE_CHECKS:
            journal.append("training", f"check:{step}", "checkpoint", {
                "step": step, "outcome": "observed_match",
                "artifact_id": "missing" if step == "saved_fields" else proof,
            })
        journal.append("training", "scenario:finish", "scenario_finish", {
            "case": "SAKAI-02", "verdict": "PASS",
        })
        with self.assertRaisesRegex(ValueError, "saved_fields"):
            training_summary(path, "training")

    def test_explorer_writes_a_candidate_with_provenance(self):
        from hashlib import sha256
        from unittest.mock import patch

        from qabro.sakai_training import SECTIONS, extract_candidate

        output = Path(self.enterContext(TemporaryDirectory())) / "candidate"
        response = "\n\n".join(f"## {section}\nUse name, description and price_cents." for section in SECTIONS)
        with patch("qabro.sakai_training.explorer_input", return_value={
            "actions": [{"step": "new", "tool": "click"}],
            "checks": [{"id": "saved", "artifact_id": "local-only"}],
        }):
            def ask(prompt):
                self.assertIn('"tool": "click"', prompt)
                self.assertNotIn("local-only", prompt)
                return response, 17

            manifest = extract_candidate(Path("unused"), "source", "a" * 64, output, ask)
        self.assertEqual(manifest["status"], "candidate")
        self.assertEqual(manifest["source_attempt_ids"], ["source"])
        self.assertEqual(manifest["extraction_tokens"], 17)
        self.assertEqual(manifest["content_sha256"], sha256((output / "SKILL.md").read_bytes()).hexdigest())
