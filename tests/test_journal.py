import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.journal import Journal


class JournalTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "runs.sqlite"
        self.journal = Journal(self.path)
        self.journal.start("a", "run", "worker1")
        self.journal.start("b", "run", "worker2")

    def test_concurrent_writes_are_ordered_and_retries_are_idempotent(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            sequences = list(pool.map(
                lambda n: self.journal.append("a", str(n), "action", {"n": n}),
                list(range(8)) * 2,
            ))
        reopened = Journal(self.path)
        self.assertEqual(sequences[:8], sequences[8:])
        self.assertEqual([entry[0] for entry in reopened.events("a")], list(range(1, 9)))
        with self.assertRaises(ValueError):
            reopened.append("a", "0", "action", {"n": 8})

    def test_tab_ownership_survives_reopen(self):
        self.assertTrue(self.journal.claim_tab("shared", "one", "a"))
        self.assertTrue(self.journal.claim_tab("shared", "two", "b"))
        reopened = Journal(self.path)
        self.assertFalse(reopened.claim_tab("shared", "one", "b"))
        self.assertFalse(reopened.release_tab("shared", "one", "b"))
        self.assertTrue(reopened.release_tab("shared", "one", "a"))
        self.assertTrue(reopened.claim_tab("shared", "one", "b"))
