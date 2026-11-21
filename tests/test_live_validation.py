"""Validate and publish a hint using fresh Chromium tabs and MCP sessions."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.artifacts import ArtifactStore
from qabro.browse_transport import BrowseTransport
from qabro.browser import BrowserCalls, Outcome
from qabro.catalog import Catalog, Scope
from qabro.contract import Checkpoint, Scenario, Step
from qabro.evidence import Evidence
from qabro.journal import Journal
from qabro.runner import Action, run_scenario
from qabro.validation import ValidationRun, validate_next_hint


@unittest.skipUnless(os.environ.get("QABRO_FIXTURE_URL"), "Set QABRO_FIXTURE_URL for the live browser test")
class LiveValidationTests(unittest.TestCase):
    def test_category_hint_is_published_with_live_evidence(self):
        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        self.assertIn(parsed.hostname, ("127.0.0.1", "localhost"))
        executable = os.environ.get("QABRO_BROWSE", "browse")
        path = Path(self.enterContext(TemporaryDirectory())) / "catalog.sqlite"
        catalog, journal, store = Catalog(path), Journal(path), ArtifactStore(path)
        scope = Scope("fixture", "select", "requirements", "editor")
        hint = "Choose a category by option value."
        catalog.jobs.enqueue("category", "validate_hint", {
            "scope": vars(scope), "summary": "Choose category", "hint": hint,
            "variants": ["select"], "variable_inputs": True,
        })
        catalog.pin("before")

        def validate(candidate):
            runs = []
            for category in ("operations", "product", "operations"):
                tab = f"validation-{uuid4().hex[:12]}"
                journal.start(tab, tab, "validator")
                self.assertTrue(journal.claim_tab("fixture", tab, tab))
                scenario = Scenario(f"Choose {category}", (
                    Step("open", "Open the fixture"),
                    Step("select", f"Choose {category}", (
                        Checkpoint("selected", f"{category.title()} is selected"),
                    )),
                ))
                actions = {
                    "open": Action("navigate", {"url": url}),
                    "select": Action("select", {"selector": "select[name=category]", "values": [category]}),
                }
                artifacts = []
                with BrowseTransport(executable) as live:
                    live.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
                    browser = BrowserCalls(journal, tab, "fixture", tab, live, lambda value: value,
                                           artifacts=store)

                    def observe(checkpoint, sample):
                        result = browser.invoke("check", "select", "snapshot", {}, read_only=True)
                        self.assertIs(result.outcome, Outcome.RETURNED)
                        self.assertIsNotNone(result.artifact_id)
                        artifacts.append((checkpoint.id, result.artifact_id))
                        text = "\n".join(item.get("text", "") for item in result.raw["content"])
                        return Evidence(monotonic_ns(), result.artifact_id,
                                        f'selected="{category.title()}"' in text)

                    try:
                        result = run_scenario(scenario, browser, lambda step: actions[step.id], observe)
                    finally:
                        live.request("tools/call", {"name": "tabs", "arguments": {"action": "close", "tab": tab}})
                journal.release_tab("fixture", tab, tab)
                runs.append(ValidationRun(candidate.ref, scope, tab, tab, category, "select",
                                          result, tuple(artifacts), tab))
            return tuple(runs)

        self.assertTrue(validate_next_hint(catalog, validate))
        catalog.pin("after")
        self.assertEqual(catalog.search("before", "category", scope, frozenset()), [])
        ref, = catalog.search("after", "category", scope, frozenset())
        self.assertEqual(catalog.load_hint("after", ref), hint)
