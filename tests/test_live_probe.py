import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.browse_transport import BrowseTransport
from qabro.browser import Outcome
from qabro.jobs import JobQueue
from qabro.journal import Journal
from qabro.probes import run_next_probe


@unittest.skipUnless(os.environ.get("QABRO_FIXTURE_URL"), "Requires the live browser fixture")
class LiveProbeTests(unittest.TestCase):
    def test_probe_creates_only_its_own_fixture_record(self):
        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        self.assertIn(parsed.hostname, ("127.0.0.1", "localhost"))
        database = Path(self.enterContext(TemporaryDirectory())) / "probe.sqlite"
        journal, queue = Journal(database), JobQueue(database)
        worker_tab = f"probe-worker-{uuid4().hex[:12]}"
        journal.start("worker", "test-run", "worker")
        journal.claim_resources("worker", ("record:worker",))
        journal.claim_tab("shared", worker_tab, "worker")
        queue.enqueue(f"fixture-create-{uuid4().hex}", "probe", {"resources": ["record:probe"]})
        actions = (
            ("navigate", {"url": url}),
            ("fill", {"selector": "input[name=name]", "value": "Probe sample"}),
            ("fill", {"selector": "input[name=date]", "value": "2027-01-20"}),
            ("click", {"selector": "button[type=submit]"}),
        )

        def execute(job, browser):
            for index, (tool, arguments) in enumerate(actions):
                self.assertIs(browser.invoke(f"op-{index}", "create", tool, arguments).outcome, Outcome.RETURNED)
            snapshot = browser.invoke("read", "create", "snapshot", {}, read_only=True)
            self.assertIn("Probe sample | 2027-01-20 | product", str(snapshot.raw))
            return {"status": "completed"}

        with BrowseTransport(os.environ.get("QABRO_BROWSE", "browse")) as live:
            opened = []

            def prepare(tab):
                live.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
                opened.append(tab)

            try:
                prepare(worker_tab)
                live(worker_tab, "navigate", {"url": url})
                live(worker_tab, "fill", {"selector": "input[name=name]", "value": "Worker sample"})
                self.assertTrue(run_next_probe(
                    queue, journal, foreground_busy=lambda: False, context="shared", transport=live,
                    redact=lambda value: value, execute=execute, prepare_tab=prepare,
                    allow_action=lambda job, tool, args: (tool, args) in actions,
                ))
                worker = live(worker_tab, "eval", {
                    "selector": "input[name=name]", "expression": "element => element.value",
                })
                self.assertIn("Worker sample", str(worker))
                self.assertNotIn("Probe sample", str(live(worker_tab, "snapshot", {})))
            finally:
                for tab in reversed(opened):
                    live(tab, "tabs", {"action": "close"})

        self.assertEqual(len(opened), 2)
        self.assertTrue(opened[1].startswith("probe-"))
        self.assertFalse(journal.claim_resources("different-worker", ("record:worker",)))
        self.assertTrue(journal.claim_resources("worker", ("record:probe",)))
