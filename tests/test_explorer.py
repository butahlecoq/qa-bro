import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Scope
from qabro.explorer import Episode, queue_exploration
from qabro.jobs import JobQueue


class ExplorerTests(unittest.TestCase):
    def test_only_recurring_costly_operations_in_the_same_scope_enter_queue(self):
        directory = self.enterContext(TemporaryDirectory())
        queue = JobQueue(Path(directory) / "jobs.sqlite")
        scope = Scope("fixture", "calendar", "requirements", "editor")
        other = Scope("fixture", "calendar", "orders", "editor")
        episodes = [
            Episode(scope, "choose date", "a", "snapshot-a", 4),
            Episode(scope, "choose date", "a", "snapshot-a2", 3),
            Episode(scope, "choose date", "b", "snapshot-b", 1, discovered_behavior=True),
            Episode(other, "choose date", "c", "snapshot-c", 4),
            Episode(scope, "click save", "a", "snapshot-d", 4, routine_action=True),
            Episode(scope, "click save", "b", "snapshot-e", 4, routine_action=True),
        ]
        job_ids = queue_exploration(queue, episodes)
        self.assertEqual(len(job_ids), 1)
        self.assertEqual(queue_exploration(queue, list(reversed(episodes))), job_ids)
        job = queue.claim("explore", now_ns=1, lease_ns=10)
        self.assertEqual(job.payload["operation"], "choose date")
        self.assertEqual(job.payload["sources"], [
            {"attempt_id": "a", "evidence_id": "snapshot-a"},
            {"attempt_id": "b", "evidence_id": "snapshot-b"},
        ])
        self.assertIsNone(queue.claim("explore", now_ns=1, lease_ns=10))
