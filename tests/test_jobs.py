import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.jobs import JobQueue


class JobTests(unittest.TestCase):
    def test_expired_job_is_reclaimed_and_stale_worker_cannot_complete_it(self):
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "runs.sqlite"
        queue = JobQueue(path)
        queue.enqueue("candidate", "validate", {"revision": "1"})
        queue.enqueue("candidate", "validate", {"revision": "1"})
        first = queue.claim("validate", now_ns=1, lease_ns=10)
        queue = JobQueue(path)
        self.assertIsNone(queue.claim("validate", now_ns=10, lease_ns=10))
        self.assertFalse(queue.complete(first, {}, now_ns=11))
        second = queue.claim("validate", now_ns=11, lease_ns=10)
        self.assertEqual(second.payload, {"revision": "1"})
        self.assertFalse(queue.complete(first, {}, now_ns=12))
        self.assertTrue(queue.complete(second, {"passed": True}, now_ns=12))
        self.assertTrue(queue.complete(second, {"passed": True}, now_ns=22))
        self.assertIsNone(queue.claim("validate", now_ns=22, lease_ns=10))

    def test_higher_priority_job_runs_first(self):
        directory = self.enterContext(TemporaryDirectory())
        queue = JobQueue(Path(directory) / "runs.sqlite")
        queue.enqueue("later", "explore", {})
        queue.enqueue("first", "explore", {}, priority=2)
        self.assertEqual(queue.claim("explore", now_ns=0, lease_ns=1).id, "first")

    def test_finalize_failure_leaves_job_available_to_retry(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        queue = JobQueue(path)
        queue.enqueue("probe", "probe", {})
        job = queue.claim("probe", now_ns=0, lease_ns=10)

        def fail(_):
            raise RuntimeError("cleanup failed")

        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            queue.complete(job, {}, now_ns=1, finalize=fail)
        self.assertIsNotNone(JobQueue(path).claim("probe", now_ns=10, lease_ns=10))
