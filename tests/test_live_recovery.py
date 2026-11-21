"""Recovery against the local fixture using a paired browse relay."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.browser import BrowserCalls
from qabro.browse_transport import BrowseTransport
from qabro.contract import Scenario, Step, Verdict
from qabro.journal import Journal
from qabro.recovery import Effect, reconcile
from qabro.runner import Action, run_scenario


@unittest.skipUnless(os.environ.get("QABRO_FIXTURE_URL"), "Set QABRO_FIXTURE_URL for the live browser test")
class LiveRecoveryTests(unittest.TestCase):
    def test_submit_reply_loss_does_not_create_duplicate(self):
        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        self.assertIn(parsed.hostname, ("127.0.0.1", "localhost"))
        executable = os.environ.get("QABRO_BROWSE", "browse")
        tab = f"recovery-{uuid4().hex[:12]}"
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "recovery.sqlite"
        journal = Journal(path)
        journal.start(tab, tab, "fixture")
        self.assertTrue(journal.claim_tab("fixture", tab, tab))

        def close_tab():
            with BrowseTransport(executable) as live:
                live.request("tools/call", {"name": "tabs", "arguments": {"action": "close", "tab": tab}})

        actions = {
            "open": Action("navigate", {"url": url}),
            "name": Action("fill", {"selector": "input[name=name]", "value": tab}),
            "date": Action("fill", {"selector": "input[name=date]", "value": "2027-01-20"}),
            "submit": Action("click", {"selector": "button[type=submit]"}),
            "inspect": Action("snapshot", {}),
        }
        scenario = Scenario("Open form, fill fields, submit, inspect list", tuple(
            Step(name, name) for name in actions
        ))

        def resolve(step):
            return actions[step.id]

        self.addCleanup(close_tab)
        with BrowseTransport(executable) as live:
            opened = live.request("tools/call", {
                "name": "tabs", "arguments": {
                    "action": "new", "id": tab, "allowedOrigins": [f"{parsed.scheme}://{parsed.netloc}"],
                },
            })
            self.assertFalse(opened.get("isError"))

            def lose_submit_response(tab_id, tool, arguments):
                result = live(tab_id, tool, arguments)
                if tool == "click":
                    self.assertFalse(result.get("isError"))
                    raise KeyboardInterrupt("Injected interruption after browser submission")
                return result

            browser = BrowserCalls(journal, tab, "fixture", tab, lose_submit_response, lambda value: value)
            with self.assertRaises(KeyboardInterrupt):
                run_scenario(scenario, browser, resolve, lambda *_: None)

        journal = Journal(path)
        self.assertEqual([action for action, _ in journal.actions_to_reconcile(tab)], ["step-3"])
        with BrowseTransport(executable) as live:
            browser = BrowserCalls(journal, tab, "fixture", tab, live, lambda value: value)

            def observe(result):
                snapshot = "\n".join(item.get("text", "") for item in result["content"])
                self.assertEqual(snapshot.count(f"{tab} | 2027-01-20 | product"), 1)
                return Effect.COMPLETED

            def recover(action, step):
                self.assertIs(reconcile(browser, action, "fresh", "snapshot", {}, observe), Effect.COMPLETED)

            attempt = run_scenario(scenario, browser, resolve, lambda *_: None, recover=recover, resume=True)
            self.assertIs(attempt.verdict, Verdict.PASS)
            self.assertEqual(attempt.completed_steps, tuple(actions))
        self.assertEqual(journal.actions_to_reconcile(tab), [])
        self.assertTrue(journal.release_tab("fixture", tab, tab))
        clicks = [event for _, event, kind, data in journal.events(tab)
                  if kind == "tool_start" and data["tool"] == "click"]
        self.assertEqual(clicks, ["step-3:start"])
