import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.artifacts import ArtifactStore
from qabro.browser import BrowserCalls
from qabro.journal import Journal
from qabro.redaction import TraceRedactor


class TraceRedactionTests(unittest.TestCase):
    def test_credentials_are_removed_before_persisting_browser_payloads(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, artifacts = Journal(path), ArtifactStore(path)
        journal.start("attempt", "run", "worker")
        journal.claim_tab("shared", "tab", "attempt")
        raw = {"content": [{"type": "text", "text": "Authorization: Bearer private\nvalue test-key"}]}
        browser = BrowserCalls(
            journal, "attempt", "shared", "tab", lambda *_: raw,
            TraceRedactor(("test-key",)), artifacts=artifacts,
        )
        result = browser.invoke("act", "step", "fill", {
            "headers": {"Set-Cookie": "private-cookie"}, "value": "test-key",
        })
        self.assertEqual(result.raw, raw)
        start = journal.events("attempt")[0][3]
        self.assertEqual(start["arguments"], {
            "headers": {"Set-Cookie": "[redacted]"}, "value": "[redacted]",
        })
        artifact = json.loads(artifacts.get(result.artifact_id))
        self.assertEqual(artifact["content"][0]["text"], "Authorization: [redacted]\nvalue [redacted]")
