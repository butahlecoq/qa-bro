import json
import unittest
from unittest.mock import Mock

from qabro.owned_row_action import OwnedRowCell, make_owned_row_dispatch


def browser_json(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class OwnedRowActionTests(unittest.TestCase):
    marker = OwnedRowCell(1, "Synthetic owned marker")
    identity = (OwnedRowCell(2, "owned-handle"), OwnedRowCell(3, "owned@example.test"))
    request = {"action": "click_owned_row", "label": "Inspect item"}

    def dispatch(self, browser, **config):
        settings = {
            "table_selector": "#approved-table", "marker": self.marker, "identity": self.identity,
            "approved_actions": frozenset({"Inspect item"}), "timeout_ms": 1000,
        }
        return make_owned_row_dispatch(browser, "owned-tab", **(settings | config))

    def test_preflight_and_click_use_the_same_strict_native_locator(self):
        browser = Mock(side_effect=[browser_json(True), browser_json({"clicked": "native receipt"})])
        result = self.dispatch(browser)(self.request)
        self.assertEqual(result, {"status": "dispatched"})
        before, clicked = [call.args for call in browser.call_args_list]
        self.assertEqual((before[0], before[1], clicked[0], clicked[1]), ("owned-tab", "eval", "owned-tab", "click"))
        selector = before[2]["selector"]
        self.assertEqual(clicked[2], {"selector": selector, "timeout": 1000})
        self.assertEqual(before[2]["world"], "isolated")
        self.assertIn("#approved-table", selector)
        self.assertIn('role=button[name="Inspect item"s]', selector)
        for column in range(1, 4):
            self.assertIn(f":nth-child({column})", selector)
        # Reject duplicate table, marker rows, and visible exact buttons even when only
        # one is currently actionable. nth is used solely in negative constraints.
        self.assertEqual(selector.count("nth=1"), 3)
        self.assertEqual(selector.count("internal:has-not="), 4)
        self.assertNotIn(self.marker.text, selector)
        self.assertIn(":scope >", selector)

    def test_worker_cannot_choose_selector_identity_labels_or_tab(self):
        browser = Mock()
        dispatch = self.dispatch(browser)
        for request in (
            {**self.request, "selector": "#untrusted"},
            {**self.request, "identity": ["another"]},
            {**self.request, "tab": "other-tab"},
            {**self.request, "label": "Inspect item "},
            {**self.request, "label": {"expression": "script"}},
            {"action": "click", "label": "Inspect item"},
        ):
            with self.subTest(request=request):
                self.assertEqual(dispatch(request), {"status": "out_of_scope"})
        browser.assert_not_called()

    def test_direct_text_is_scoped_and_guarded_against_duplicate_candidates(self):
        marker = OwnedRowCell(1, self.marker.text, "div.name")
        browser = Mock(side_effect=[browser_json(True), browser_json({"clicked": "native receipt"})])
        self.assertEqual(self.dispatch(browser, marker=marker)(self.request), {"status": "dispatched"})
        read, click = [call.args[2]["selector"] for call in browser.call_args_list]
        self.assertEqual(read, click)
        self.assertEqual(read.count("text:light="), 2)
        self.assertEqual(read.count("nth=1"), 4)
        self.assertIn("css:light=:scope > div.name:visible", read)
        self.assertIn(":nth-child(1)", read)
        for selector in ("div > span", "div,span", "div >> frame >> #draft", ":scope *"):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                OwnedRowCell(1, self.marker.text, selector)

    def test_icon_fallback_uses_host_bound_direct_icon_without_empty_name_predicate(self):
        browser = Mock(side_effect=[browser_json(True), browser_json({"clicked": "native receipt"})])
        dispatch = self.dispatch(browser, action_icons={"Inspect item": "span.approved-icon"},
                                 action_columns={"Inspect item": 9})
        self.assertEqual(dispatch(self.request), {"status": "dispatched"})
        read, click = [call.args[2]["selector"] for call in browser.call_args_list]
        self.assertEqual(read, click)
        self.assertIn("role=button", read)
        self.assertNotIn("name=", read)
        self.assertIn(":scope > span.approved-icon:visible", read)
        self.assertIn(":scope > :nth-child(9)", read)
        self.assertEqual(read.count("nth=1"), 4)
        for config in ({"Inspect item": "span >> nth=3"}, {"unapproved": "span"}):
            with self.assertRaises(ValueError):
                self.dispatch(browser, action_icons=config)

    def test_unverified_preflight_never_calls_click(self):
        for payload in (browser_json(False), browser_json({"visible_matches": 1}),
                        {"isError": True}, browser_json("unowned row data"), TimeoutError("private")):
            browser = Mock(side_effect=[payload])
            result = self.dispatch(browser)(self.request)
            self.assertEqual(result, {"status": "not_actionable"})
            browser.assert_called_once()
            self.assertEqual(browser.call_args.args[1], "eval")

    def test_click_error_is_an_unknown_effect_without_retry_or_raw_text(self):
        for result in (TimeoutError("private"), browser_json({"raw_row": "private"}),
                       {"isError": True, "content": [{"type": "text", "text": "private"}]}):
            browser = Mock(side_effect=[browser_json(True), result])
            self.assertEqual(self.dispatch(browser)(self.request), {"status": "unknown_effect"})
            self.assertEqual([call.args[1] for call in browser.call_args_list], ["eval", "click"])

    def test_click_accepts_a_bounded_receipt_echoing_the_long_native_selector(self):
        marker = OwnedRowCell(self.marker.column, "Owned marker " * 8, "div")
        identity = (OwnedRowCell(2, "owned-email" * 10), OwnedRowCell(3, "owned-user" * 10))

        def native(_tab, tool, args):
            if tool == "eval":
                return browser_json(True)
            reply = browser_json({"clicked": args["selector"]})
            self.assertGreater(len(reply["content"][0]["text"]), 4096)
            return reply

        browser = Mock(side_effect=native)
        dispatch = self.dispatch(browser, marker=marker, identity=identity)
        self.assertEqual(dispatch(self.request), {"status": "dispatched"})
        self.assertEqual([call.args[1] for call in browser.call_args_list], ["eval", "click"])

    def test_ambiguous_or_unencodable_identity_bindings_are_rejected_before_use(self):
        browser = Mock()
        for config in (
            {"identity": (OwnedRowCell(1, "owned-handle"),)},
            {"identity": (OwnedRowCell(2, self.marker.text),)},
            {"identity": ()},
            {"table_selector": "table >> nth=2"},
            {"approved_actions": frozenset()},
            {"timeout_ms": 0},
        ):
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    self.dispatch(browser, **config)
        browser.assert_not_called()
