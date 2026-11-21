import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.browser import BrowserCalls, Outcome, normalize
from qabro.journal import DuplicateEvent, Journal


class BrowserTests(unittest.TestCase):
    def test_mcp_response_categories(self):
        self.assertEqual(normalize({"content": [{"type": "text", "text": "ready"}]}), Outcome.RETURNED)
        self.assertEqual(normalize({"isError": True, "content": []}), Outcome.TOOL_ERROR)
        self.assertEqual(normalize({"content": "garbled"}), Outcome.UNKNOWN)

    def test_timeout_records_unknown_and_reserves_action_against_blind_retry(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")

        def transport(tab, tool, arguments):
            raise TimeoutError("sensitive transport text")

        browser = BrowserCalls(journal, "attempt", "tab", transport, lambda _: "[redacted]")
        with self.assertRaises(TimeoutError):
            browser.invoke("save", "step-1", "click", {"secret": "value"})
        with self.assertRaises(DuplicateEvent):
            browser.invoke("save", "step-1", "click", {"secret": "value"})
        start, finish = journal.events("attempt")
        self.assertEqual(start[3]["arguments"], "[redacted]")
        self.assertEqual(finish[3]["outcome"], Outcome.UNKNOWN)
        self.assertEqual(finish[3]["raw"], {"exception": "TimeoutError"})
