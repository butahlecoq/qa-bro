import json
import os
import unittest
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.browse_transport import BrowseTransport
from qabro.compiled_browser import Operation, compile_operations
from qabro.runner import Action


@unittest.skipUnless(os.environ.get("QABRO_FIXTURE_URL"), "Requires the live browser fixture")
class LiveCompiledBrowserTests(unittest.TestCase):
    def test_reports_prefix_and_stops_after_an_unmatched_checkpoint(self):
        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        tab = f"compiled-{uuid4().hex}"
        operations = (
            Operation("open", Action("navigate", {"url": url})),
            Operation("name", Action("fill", {"selector": "input[name=name]", "value": "Compiled sample"})),
            Operation("check", Action("snapshot", {}), "Definitely absent checkpoint"),
            Operation("replace", Action("fill", {"selector": "input[name=name]", "value": "Must not run"})),
        )
        with BrowseTransport(os.environ.get("QABRO_BROWSE", "browse"), include_execute=True) as browser:
            browser.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
            try:
                result = browser(tab, "execute", compile_operations(operations, timeout_ms=5000))
                self.assertFalse(result.get("isError", False), result)
                _, payload = result["content"][0]["text"].split("\n\n", 1)
                events = json.JSONDecoder().raw_decode(payload)[0]["events"]
                self.assertEqual(
                    [(event["step"], event["outcome"]) for event in events],
                    [("open", "returned"), ("name", "returned"), ("check", "mismatched")],
                )
                field = browser(tab, "eval", {
                    "selector": "input[name=name]", "expression": "element => element.value",
                })
                self.assertEqual(json.loads(field["content"][0]["text"]), "Compiled sample")
            finally:
                browser(tab, "tabs", {"action": "close"})

    def test_compare_backends_and_detect_incomplete_timeout_trace(self):
        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        opening = Operation("open", Action("navigate", {"url": url}))
        fill = Operation("name", Action("fill", {
            "selector": "input[name=name]", "value": "First value",
        }))
        replace = Operation("replace", Action("fill", {
            "selector": "input[name=name]", "value": "Second value",
        }))
        cases = {
            "success": (Operation("check", Action("snapshot", {}), "Requirements"), "Second value"),
            "checkpoint failure": (
                Operation("check", Action("snapshot", {}), "Definitely absent checkpoint"), "First value",
            ),
            "partial effect": (
                Operation("check", Action("fill", {"selector": "#missing", "value": "Ignored"})),
                "First value",
            ),
        }
        with BrowseTransport(os.environ.get("QABRO_BROWSE", "browse"), include_execute=True) as browser:
            for case, (probe, expected_value) in cases.items():
                with self.subTest(case=case):
                    operations = (opening, fill, probe, replace)
                    traces = {}
                    for backend in ("plain", "compiled"):
                        tab = f"compiled-{uuid4().hex}"
                        browser.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
                        try:
                            if backend == "compiled":
                                result = browser(tab, "execute", compile_operations(operations, timeout_ms=5000))
                                if result.get("isError"):
                                    message = result["content"][0]["text"]
                                    self.assertIn("execute timed out", message)
                                    _, markers = message.split("\n\nConsole:\n", 1)
                                    self.assertEqual(markers.splitlines(), [
                                        "qa-bro: 0 started", "qa-bro: 0 returned",
                                        "qa-bro: 1 started", "qa-bro: 1 returned", "qa-bro: 2 started",
                                    ])
                                    traces[backend] = None
                                else:
                                    _, payload = result["content"][0]["text"].split("\n\n", 1)
                                    events = json.JSONDecoder().raw_decode(payload)[0]["events"]
                                    traces[backend] = [(event["step"], event["outcome"]) for event in events]
                            else:
                                trace = []
                                for operation in operations:
                                    action = operation.action
                                    result = browser(tab, action.tool, action.arguments)
                                    outcome = "returned"
                                    if result.get("isError"):
                                        outcome = "unknown"
                                    elif operation.expected_text is not None:
                                        snapshot = result["content"][0]["text"]
                                        outcome = "matched" if operation.expected_text in snapshot else "mismatched"
                                    trace.append((operation.step, outcome))
                                    if outcome in {"unknown", "mismatched"}:
                                        break
                                traces[backend] = trace
                            field = browser(tab, "eval", {
                                "selector": "input[name=name]", "expression": "element => element.value",
                            })
                            self.assertEqual(json.loads(field["content"][0]["text"]), expected_value)
                        finally:
                            browser(tab, "tabs", {"action": "close"})
                    if case == "partial effect":
                        self.assertEqual(traces["plain"], [
                            ("open", "returned"), ("name", "returned"), ("check", "unknown"),
                        ])
                        self.assertIsNone(traces["compiled"])
                    else:
                        self.assertEqual(traces["plain"], traces["compiled"])
