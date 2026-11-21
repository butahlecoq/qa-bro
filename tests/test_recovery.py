import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.browser import BrowserCalls
from qabro.journal import Journal
from qabro.recovery import Effect, reconcile


class RecoveryTests(unittest.TestCase):
    def test_fresh_snapshot_confirms_submit_that_timed_out(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        records = []

        def transport(tab, tool, arguments):
            if tool == "submit":
                records.append("requirement-1")
                raise TimeoutError()
            return {"content": [{"type": "text", "text": "snapshot"}], "structuredContent": {
                "ids": records.copy(),
            }}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        with self.assertRaises(TimeoutError):
            browser.invoke("create", "submit-step", "submit", {})
        journal = Journal(journal.path)
        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        evaluate = lambda raw: (
            Effect.COMPLETED if "requirement-1" in raw["structuredContent"]["ids"] else Effect.UNKNOWN
        )
        self.assertEqual(
            reconcile(browser, "create", "inspect-create", "snapshot", {}, evaluate),
            Effect.COMPLETED,
        )
        self.assertEqual(records, ["requirement-1"])
        self.assertEqual(journal.actions_to_reconcile("attempt"), [])
        self.assertEqual(journal.events("attempt")[-1][3]["probe_event_id"], "inspect-create:finish")
