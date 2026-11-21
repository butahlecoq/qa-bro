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

    def test_resource_claim_is_all_or_nothing_and_survives_restart(self):
        self.assertTrue(self.journal.claim_resources("a", ("record:42",)))
        reopened = Journal(self.path)
        self.assertFalse(reopened.claim_resources("b", ("other", "record:42")))
        self.assertTrue(reopened.claim_resources("a", ("other",)))
        reopened.release_resources("b")
        self.assertFalse(reopened.claim_resources("b", ("record:42",)))
        reopened.release_resources("a")
        self.assertTrue(reopened.claim_resources("b", ("record:42", "other")))

    def test_resource_release_requires_reconciled_effects(self):
        self.journal.claim_resources("a", ("record:42",))
        self.journal.append("a", "save:start", "tool_start", {"step": "save"})
        with self.assertRaises(RuntimeError):
            self.journal.release_resources("a")
        self.assertFalse(self.journal.claim_resources("b", ("record:42",)))

    def test_prune_keeps_full_retry_history_while_any_evidence_is_pinned(self):
        from qabro.artifacts import ArtifactStore

        store = ArtifactStore(self.path)
        proof = store.put(b"previous failure", now=0, owner="skill")
        self.journal.append("a", "check:saved", "checkpoint", {"artifact_id": proof})
        self.journal.append("a", "scenario:finish", "scenario_finish", {"verdict": "FAIL"})
        self.journal.append("b", "scenario:finish", "scenario_finish", {"verdict": "PASS"})
        self.assertGreater(self.journal.prune(before_ns=0, max_payload_bytes=0), 0)
        self.assertTrue(self.journal.events("b"))
        store.unpin("skill")
        self.assertEqual(self.journal.prune(before_ns=0, max_payload_bytes=0), 0)
        self.assertEqual(self.journal.events("a"), [])
        self.assertEqual(self.journal.events("b"), [])
        with self.assertRaisesRegex(ValueError, "pruned"):
            self.journal.append("a", "scenario:start", "scenario_start", {})

    def test_child_tab_can_only_be_claimed_via_owned_parent(self):
        self.assertTrue(self.journal.claim_tab("shared", "parent-a", "a"))
        self.assertTrue(self.journal.claim_tab("shared", "parent-b", "b"))
        self.assertFalse(self.journal.claim_tab("shared", "child", "b", parent="parent-a"))
        self.assertTrue(self.journal.claim_tab("shared", "child", "a", parent="parent-a"))
        reopened = Journal(self.path)
        self.assertFalse(reopened.claim_tab("shared", "child", "b", parent="parent-b"))
        self.assertTrue(reopened.claim_tab("shared", "child", "a", parent="parent-a"))
