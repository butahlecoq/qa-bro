"""Recovery against the local fixture using a paired browse relay."""

import os
import unittest
from multiprocessing import get_context
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


def submit_and_exit(executable, path, tab, scenario, actions):
    journal = Journal(path)
    with BrowseTransport(executable) as live:
        def lose_submit_response(tab_id, tool, arguments):
            result = live(tab_id, tool, arguments)
            if tool == "click" and not result.get("isError"):
                os._exit(17)
            return result

        browser = BrowserCalls(journal, tab, "fixture", tab, lose_submit_response, lambda value: value)
        run_scenario(scenario, browser, lambda step: actions[step.id], lambda *_: None)


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

        process = get_context("spawn").Process(
            target=submit_and_exit, args=(executable, path, tab, scenario, actions),
        )
        process.start()
        try:
            process.join(timeout=30)
            self.assertEqual(process.exitcode, 17)
        finally:
            if process.is_alive():
                process.kill()
                process.join()
            process.close()

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

    def test_workers_share_browser_context_and_only_opener_owns_popup(self):
        from qabro.browser import Outcome, claim_child_tabs

        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        self.assertIn(parsed.hostname, ("127.0.0.1", "localhost"))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = Path(self.enterContext(TemporaryDirectory())) / "tabs.sqlite"
        journal = Journal(path)
        tabs = [f"worker-{uuid4().hex[:12]}" for _ in range(2)]
        children = ()
        with BrowseTransport(os.environ.get("QABRO_BROWSE", "browse")) as live:
            try:
                browsers = []
                for tab in tabs:
                    live.prepare_tab(tab, allowed_origins=(origin,))
                    journal.start(tab, "shared-run", tab)
                    self.assertTrue(journal.claim_tab("shared", tab, tab))
                    browser = BrowserCalls(journal, tab, "shared", tab, live, lambda value: value)
                    self.assertIs(browser.invoke("open", "open", "navigate", {"url": url}).outcome,
                                  Outcome.RETURNED)
                    browsers.append(browser)
                parent, other = browsers
                cookie = f"{parent.tab}=shared; path=/"
                self.assertIs(parent.invoke("cookie", "fixture-context", "eval", {
                    "expression": "(element, cookie) => { document.cookie = cookie; return true; }",
                    "arg": cookie,
                }).outcome, Outcome.RETURNED)
                shared = other.invoke("cookie", "fixture-context", "eval", {
                    "expression": "document.cookie",
                }, read_only=True)
                self.assertIs(shared.outcome, Outcome.RETURNED)
                self.assertIn(f"{parent.tab}=shared", str(shared.raw))
                opened = parent.invoke("popup", "popup", "eval", {
                    "expression": "window.open(location.href, '_blank'); true",
                })
                self.assertIs(opened.outcome, Outcome.RETURNED)
                from time import sleep

                for sample in range(10):
                    children = claim_child_tabs(parent, f"tabs-{sample}", "popup")
                    if children:
                        break
                    sleep(0.1)
                self.assertEqual(len(children), 1)
                child, = children
                self.assertFalse(Journal(path).claim_tab("shared", child, other.attempt, parent=other.tab))
                self.assertEqual(claim_child_tabs(other, "tabs", "popup"), ())
            finally:
                live(tabs[0], "eval", {
                    "expression": "(element, cookie) => { document.cookie = cookie; }",
                    "arg": f"{tabs[0]}=; path=/; Max-Age=0",
                })
                for tab in (*tabs, *children):
                    live.request("tools/call", {"name": "tabs", "arguments": {"action": "close", "tab": tab}})
