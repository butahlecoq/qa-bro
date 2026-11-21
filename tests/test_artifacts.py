import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.artifacts import ArtifactStore


class ArtifactTests(unittest.TestCase):
    def test_prune_respects_age_size_and_multiple_pins(self):
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "artifacts.sqlite"
        store = ArtifactStore(path)
        pinned = store.put(b"pin", now=1, owner="skill:1")
        self.assertEqual(store.put(b"pin", now=1, owner="skill:2"), pinned)
        expired = store.put(b"old", now=1)
        excess = store.put(b"excess", now=5)
        newest = store.put(b"new", now=6)
        store = ArtifactStore(path)
        store.unpin("skill:1")
        self.assertEqual(store.prune(before=4, max_bytes=6), 6)
        self.assertIsNone(store.get(expired))
        self.assertIsNone(store.get(excess))
        self.assertEqual(store.get(newest), b"new")
        self.assertEqual(store.get(pinned), b"pin")
        self.assertEqual(store.prune(before=10, max_bytes=0), 3)
        store.unpin("skill:2")
        self.assertEqual(store.prune(before=10, max_bytes=0), 0)

    def test_retention_preserves_evidence_in_an_incomplete_attempt(self):
        from qabro.journal import Journal
        from qabro.retention import prune_database

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, store = Journal(path), ArtifactStore(path)
        journal.start("attempt", "run", "worker")
        proof = store.put(b"recovery evidence", now=1)
        journal.append("attempt", "probe:finish", "tool_finish", {"artifact_id": proof})
        unused = store.put(b"unused", now=1)
        result = prune_database(path, before_ns=2, journal_bytes=0, artifact_bytes=0)
        self.assertFalse(result["within_limits"])
        self.assertEqual(store.get(proof), b"recovery evidence")
        self.assertIsNone(store.get(unused))

    def test_reset_evidence_survives_while_restart_is_retained(self):
        from qabro.journal import Journal
        from qabro.retention import prune_database

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, store = Journal(path), ArtifactStore(path)
        journal.start("first", "run", "worker")
        journal.append("first", "scenario:finish", "scenario_finish", {"verdict": "FAIL"})
        proof = store.put(b"reset evidence", now=1)
        journal.start("retry", "run", "worker", restart_of="first", setup_artifact_id=proof)
        self.assertFalse(prune_database(path, before_ns=2, journal_bytes=0, artifact_bytes=0)["within_limits"])
        self.assertEqual(store.get(proof), b"reset evidence")
        journal.append("retry", "scenario:finish", "scenario_finish", {"verdict": "PASS"})
        self.assertTrue(prune_database(path, before_ns=2, journal_bytes=0, artifact_bytes=0)["within_limits"])
        self.assertIsNone(store.get(proof))
