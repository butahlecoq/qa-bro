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
