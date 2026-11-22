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

        from qabro.sakai_training import extract_candidate

        output = Path(self.enterContext(TemporaryDirectory())) / "candidate"
        response = '{"selector":"#price"}'
        with patch("qabro.sakai_training.explorer_input", return_value={
            "interaction": {"component": "Price", "tool": "fill", "selector": "#price"},
            "checks": [{"id": "saved", "artifact_id": "local-only"}],
        }):
            def ask(prompt):
                self.assertIn('"tool": "fill"', prompt)
                self.assertNotIn("local-only", prompt)
                return response, 17

            manifest = extract_candidate(Path("unused"), "source", "a" * 64, output, ask)
        self.assertEqual(manifest["status"], "candidate")
        self.assertEqual(manifest["source_attempt_ids"], ["source"])
        self.assertEqual(manifest["extraction_tokens"], 17)
        self.assertEqual(manifest["content_sha256"], sha256((output / "SKILL.md").read_bytes()).hexdigest())

    def test_activation_requires_two_independent_workers_using_the_exact_candidate(self):
        import json
        from hashlib import sha256

        from qabro.sakai_training import activate_candidate

        root = Path(self.enterContext(TemporaryDirectory()))
        path = root / "worker.sqlite"
        candidate = root / "candidate"
        candidate.mkdir()
        body = b"# Candidate\n"
        (candidate / "SKILL.md").write_bytes(body)
        digest = sha256(body).hexdigest()
        manifest = {
            "status": "candidate", "source_attempt_ids": ["source"],
            "content_sha256": digest, "browser_capabilities_sha256": "a" * 64,
        }
        (candidate / "manifest.json").write_text(json.dumps(manifest))
        journal, store = Journal(path), ArtifactStore(path)
        proof = store.put(b"evidence fixture", now=1)
        for seed, attempt in enumerate(("source", "fallback", "v1", "v2")):
            journal.start(attempt, "series", "worker")
            journal.append(attempt, "sakai:worker", "worker_metadata", {
                "seed": seed, "session_id": attempt,
                "browser_schema_sha256": "a" * 64, "scenario_sha256": "b" * 64,
                "skill_sha256": None if attempt == "source" else digest,
                "skill_applied": attempt.startswith("v"),
            })
            for step in CREATE_CHECKS:
                journal.append(attempt, f"check:{step}", "checkpoint", {
                    "step": step, "outcome": "observed_match", "artifact_id": proof,
                })
            journal.append(attempt, "scenario:finish", "scenario_finish", {
                "case": "SAKAI-02", "verdict": "PASS",
            })
        with self.assertRaisesRegex(ValueError, "exact candidate"):
            activate_candidate(candidate, path, ((path, "fallback"), (path, "v1")))
        self.assertEqual(json.loads((candidate / "manifest.json").read_text())["status"], "candidate")
        active = activate_candidate(candidate, path, ((path, "v1"), (path, "v2")))
        self.assertEqual(active["validation_attempt_ids"], ["v1", "v2"])
        self.assertEqual(json.loads((candidate / "manifest.json").read_text())["status"], "active")

    def test_training_orchestration_keeps_candidate_inactive_during_validation(self):
        import json
        from hashlib import sha256
        from unittest.mock import patch

        from qabro.sakai_training import train_sakai

        root = Path(self.enterContext(TemporaryDirectory()))
        database = root / "worker.sqlite"
        output = root / "candidate"
        journal, store = Journal(database), ArtifactStore(database)
        artifact = store.put(b"proof", now=1)
        calls = []

        def worker(seed, skill):
            calls.append(seed)
            if skill:
                self.assertEqual(json.loads((output / "manifest.json").read_text())["status"], "candidate")
            attempt = f"attempt-{seed}"
            journal.start(attempt, "series", "worker")
            journal.append(attempt, "sakai:worker", "worker_metadata", {
                "seed": seed, "session_id": attempt, "browser_schema_sha256": "a" * 64,
                "scenario_sha256": "b" * 64, "skill_applied": skill is not None,
                "skill_sha256": sha256(skill.read_bytes()).hexdigest() if skill else None,
            })
            for step in CREATE_CHECKS:
                journal.append(attempt, f"check:{step}", "checkpoint", {
                    "step": step, "outcome": "observed_match", "artifact_id": artifact,
                })
            journal.append(attempt, "scenario:finish", "scenario_finish", {"case": "SAKAI-02", "verdict": "PASS"})
            return database, attempt

        def explorer(_):
            calls.append("explorer")
            return '{"selector":"#price"}', 12

        with patch("qabro.sakai_training.explorer_input", return_value={"interaction": {"selector": "#price"}}):
            active = train_sakai(output, "a" * 64, (1, 2, 3), worker, explorer)
        self.assertEqual(calls, [1, "explorer", 2, 3])
        self.assertEqual(active["status"], "active")
