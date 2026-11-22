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
