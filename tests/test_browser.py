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

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda _: "[redacted]")
        with self.assertRaises(PermissionError):
            browser.invoke("save", "step-1", "click", {})
        self.assertEqual(journal.events("attempt"), [])
        journal.claim_tab("shared", "tab", "attempt")
        with self.assertRaises(TimeoutError):
            browser.invoke("save", "step-1", "click", {"secret": "value"})
        with self.assertRaises(DuplicateEvent):
            browser.invoke("save", "step-1", "click", {"secret": "value"})
        start, finish = journal.events("attempt")
        self.assertEqual(start[3]["arguments"], "[redacted]")
        self.assertEqual(finish[3]["outcome"], Outcome.UNKNOWN)
        self.assertEqual(finish[3]["raw"], {"exception": "TimeoutError"})

        reopened = Journal(journal.path)
        self.assertEqual(reopened.actions_to_reconcile("attempt"), [("save", start[3])])
        self.assertFalse(reopened.release_tab("shared", "tab", "attempt"))
        reopened.append("attempt", "save:reconciled", "reconciliation", {
            "artifact_id": "fresh-snapshot", "effect": "completed",
        })
        self.assertEqual(reopened.actions_to_reconcile("attempt"), [])
        self.assertTrue(reopened.release_tab("shared", "tab", "attempt"))

    def test_active_action_keeps_tab_until_call_finishes(self):
        directory = self.enterContext(TemporaryDirectory())
        journal = Journal(Path(directory) / "runs.sqlite")
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")

        def transport(tab, tool, arguments):
            self.assertFalse(journal.release_tab("shared", tab, "attempt"))
            return {"content": [{"type": "text", "text": "ready"}]}

        browser = BrowserCalls(journal, "attempt", "shared", "tab", transport, lambda value: value)
        self.assertEqual(browser.invoke("read", "step-1", "snapshot", {}).outcome, Outcome.RETURNED)
        self.assertTrue(journal.release_tab("shared", "tab", "attempt"))

    def test_result_references_redacted_artifact(self):
        import json

        from qabro.artifacts import ArtifactStore

        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "runs.sqlite"
        journal = Journal(path)
        artifacts = ArtifactStore(path)
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        raw = {"content": [{"type": "text", "text": "credential"}]}
        redacted = {"content": [{"type": "text", "text": "[redacted]"}]}
        browser = BrowserCalls(
            journal, "attempt", "shared", "tab", lambda tab, tool, arguments: raw,
            lambda value: redacted if value == raw else value, artifacts=artifacts,
        )
        result = browser.invoke("inspect", "open", "snapshot", {}, read_only=True)
        self.assertEqual(result.raw, raw)
        finish = journal.events("attempt")[-1][3]
        self.assertNotIn("raw", finish)
        self.assertEqual(finish["artifact_id"], result.artifact_id)
        self.assertEqual(json.loads(artifacts.get(result.artifact_id)), redacted)
