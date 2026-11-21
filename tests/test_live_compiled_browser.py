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
