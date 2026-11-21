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
        wrong_hint = "Always choose Product."
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
                selected_value = "product" if candidate.hint == wrong_hint else category
                actions = {
                    "open": Action("navigate", {"url": url}),
                    "select": Action("select", {"selector": "select[name=category]", "values": [selected_value]}),
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

        catalog.jobs.enqueue("wrong-category", "validate_hint", {
            "scope": vars(scope), "summary": "Choose category", "hint": wrong_hint,
            "variants": ["select"], "variable_inputs": True,
        })
        self.assertTrue(validate_next_hint(catalog, validate))
        catalog.pin("after-rejection")
        self.assertEqual(catalog.search("after-rejection", "category", scope, frozenset()), [ref])

    def test_changed_snapshot_schema_triggers_a_live_compatibility_check(self):
        from copy import deepcopy

        from qabro.browse_schema import snapshot_schema
        from qabro.compatibility import check_browse_upgrade

        executable = os.environ.get("QABRO_BROWSE", "browse")
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        tab = f"compatibility-{uuid4().hex[:12]}"
        journal.start(tab, tab, "validator")
        journal.claim_tab("fixture", tab, tab)
        with BrowseTransport(executable) as live:
            live.prepare_tab(tab, allowed_origins=("http://127.0.0.1:18765",))
            try:
                previous = deepcopy(snapshot_schema(live))
                snapshot = next(tool for tool in previous["tools"] if tool["name"] == "snapshot")
                snapshot["inputSchema"]["required"].append("old_argument")
                browser = BrowserCalls(journal, tab, "fixture", tab, live, lambda value: value)

                def smoke(adapter):
                    result = adapter.invoke("smoke-snapshot", "check", "snapshot", {}, read_only=True)
                    return result.outcome is Outcome.RETURNED

                self.assertEqual(check_browse_upgrade(
                    browser, live, previous, {"snapshot": smoke}, frozenset({"snapshot", "status"}),
                ), frozenset({"snapshot", "status"}))
                self.assertEqual([kind for _, _, kind, _ in journal.events(tab)], [
                    "browser_schema", "tool_start", "tool_finish", "compatibility_check",
                ])
            finally:
                live.request("tools/call", {"name": "tabs", "arguments": {"action": "close", "tab": tab}})
