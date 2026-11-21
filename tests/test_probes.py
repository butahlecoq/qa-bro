import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.jobs import JobQueue
from qabro.journal import Journal
from qabro.probes import run_next_probe


class ProbeTests(unittest.TestCase):
    def test_probe_defers_under_load_and_while_worker_owns_resource(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, queue = Journal(path), JobQueue(path)
        journal.start("worker", "run", "worker")
        journal.claim_tab("shared", "worker-tab", "worker")
        journal.claim_resources("worker", ("record:test",))
        queue.enqueue("one", "probe", {"resources": ["record:test"]})
        calls = []

        def transport(tab, tool, arguments):
            calls.append((tab, tool))
            return {"content": [{"type": "text", "text": "done"}]}

        def execute(job, browser):
            result = browser.invoke("modify", "probe", "click", {})
            return {"outcome": result.outcome}

        args = {"context": "shared", "transport": transport,
                "redact": lambda value: value, "execute": execute}
        self.assertFalse(run_next_probe(queue, journal, **args, foreground_busy=lambda: True, clock=lambda: 0))
        self.assertFalse(run_next_probe(queue, journal, **args, foreground_busy=lambda: False, clock=lambda: 0))
        self.assertEqual(calls, [])
        journal.release_resources("worker")
        self.assertTrue(run_next_probe(
            JobQueue(path), Journal(path), **args, foreground_busy=lambda: False,
            clock=lambda: 60_000_000_000,
        ))
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].startswith("probe-"))
        self.assertFalse(journal.claim_tab("shared", "worker-tab", "probe:one"))
        self.assertTrue(journal.claim_resources("worker", ("record:test",)))
