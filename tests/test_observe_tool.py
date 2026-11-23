import json
import unittest
from unittest.mock import Mock, patch

from qabro.observe_tool import make_observe_dispatch


def browser_json(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class ObserveToolTests(unittest.TestCase):
    def test_blur_presses_only_tab_on_the_focused_guarded_field_and_reobserves(self):
        browser = Mock(side_effect=[
            browser_json(False),
            browser_json(True), browser_json({"pressed": ["Tab"], "target": "private"}), browser_json(False),
            browser_json(True), browser_json({"pressed": ["Tab"]}), browser_json(True),
        ])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Email"}, dialog_fields={"Email": {"sample": "value"}},
        )
        request = {"action": "blur_dialog_field", "label": "Email"}
        self.assertEqual(dispatch({**request, "key": "Enter"}), {"status": "out_of_scope"})
        self.assertEqual(dispatch({**request, "parameter": "sample"}), {"status": "out_of_scope"})
        browser.assert_not_called()
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertEqual(dispatch(request), {"status": "ok", "blurred": True})
        self.assertEqual(dispatch(request), {"status": "ok", "blurred": False})
        _, preflight, press, read, *_ = [call.args for call in browser.call_args_list]
        self.assertEqual(press, ("owned-tab", "press", {"selector": preflight[2]["selector"], "key": "Tab"}))
        self.assertEqual(preflight[2]["arg"], {"check": "focused"})
        self.assertEqual(preflight, read)

    def test_blur_needs_independent_focus_evidence_after_a_native_press(self):
        browser = Mock(side_effect=[
            browser_json(True), browser_json({"pressed": "private"}),
            browser_json(True), browser_json({"pressed": ["Tab"]}), browser_json(None),
        ])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Email"}, dialog_fields={"Email": {}},
        )
        request = {"action": "blur_dialog_field", "label": "Email"}
        self.assertEqual(dispatch(request), {"status": "unknown_effect"})
        self.assertEqual(dispatch(request), {"status": "unknown_effect"})

    def test_dialog_text_only_releases_approved_count_and_distinguishes_no_dialog(self):
        browser = Mock(side_effect=[browser_json(value) for value in
                                    ("none", "one", "multiple", "no_dialog", "private data")])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(), dialog_texts={"Expected validation"},
        )
        request = {"action": "observe_dialog_text", "text": "Expected validation"}
        self.assertEqual(dispatch({**request, "text": "arbitrary text"}), {"status": "out_of_scope"})
        self.assertEqual(dispatch({**request, "selector": "body"}), {"status": "out_of_scope"})
        browser.assert_not_called()
        for bucket in ("none", "one", "multiple"):
            self.assertEqual(dispatch(request), {"status": "ok", "visible_matches": bucket})
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertEqual(dispatch(request), {"status": "malformed"})
        self.assertTrue(all(call.args[1] == "eval" for call in browser.call_args_list))

    def test_dialog_action_observes_one_approved_button_even_when_disabled(self):
        browser = Mock(side_effect=[browser_json(False), browser_json(True), browser_json("private")])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Save", "Cancel"}, dialog_action_labels={"Save"},
        )
        request = {"action": "observe_dialog_action", "label": "Save"}
        self.assertEqual(dispatch({**request, "label": "Cancel"}), {"status": "out_of_scope"})
        browser.assert_not_called()
        self.assertEqual(dispatch(request), {"status": "ok", "enabled": False})
        self.assertEqual(dispatch(request), {"status": "ok", "enabled": True})
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertTrue(all(call.args[1] == "eval" for call in browser.call_args_list))

    def test_dialog_click_requires_an_authorized_text_and_button_pair(self):
        browser = Mock()
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Confirm", "Close"},
            dialog_texts={"Discard draft", "Sign out"}, dialog_action_labels={"Confirm"},
            dialog_click_actions={"Discard draft": {"Confirm"}, "Sign out": {"Close"}},
        )
        request = {"action": "click_dialog_action", "text": "Discard draft", "label": "Confirm"}
        for denied in (
            {**request, "text": "Sign out"}, {**request, "label": "Close"},
            {**request, "selector": "button"}, {"action": "click", "label": "Confirm"},
        ):
            self.assertEqual(dispatch(denied), {"status": "out_of_scope"})
        browser.assert_not_called()

    def test_dialog_click_reuses_the_scoped_non_submit_locator_for_native_action(self):
        browser = Mock(side_effect=[browser_json(True), browser_json({"clicked": "private diagnostic"})])
        allowed_actions = {"Confirm"}
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Confirm"},
            dialog_texts={"Discard draft"}, dialog_click_actions={"Discard draft": allowed_actions},
        )
        allowed_actions.clear()
        request = {"action": "click_dialog_action", "text": "Discard draft", "label": "Confirm"}
        self.assertEqual(dispatch(request), {"status": "dispatched"})
        preflight, click = [call.args for call in browser.call_args_list]
        self.assertEqual(preflight[:2], ("owned-tab", "eval"))
        self.assertEqual(preflight[2]["arg"], "Discard draft")
        self.assertEqual(click, ("owned-tab", "click", {"selector": preflight[2]["selector"]}))
        selector = click[2]["selector"]
        self.assertTrue(selector.startswith("css=:is(dialog[open]"))
        self.assertIn("internal:has=", selector)
        self.assertIn('role=button[name="Confirm"s]', selector)
        self.assertIn('[type="submit" i]', json.loads(selector.rsplit("internal:and=", 1)[1]))

    def test_dialog_click_does_not_act_on_ambiguous_or_failed_preflight(self):
        browser = Mock(side_effect=[
            browser_json(False), {"isError": True, "content": ["private native response"]},
            browser_json(True), browser_json({"private": "unexpected click response"}),
        ])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Confirm"},
            dialog_texts={"Discard draft"}, dialog_click_actions={"Discard draft": {"Confirm"}},
        )
        request = {"action": "click_dialog_action", "text": "Discard draft", "label": "Confirm"}
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertEqual([call.args[1] for call in browser.call_args_list], ["eval", "eval"])
        self.assertEqual(dispatch(request), {"status": "unknown_effect"})

    def test_dialog_fields_use_only_parameters_bound_to_an_exact_label(self):
        browser = Mock()
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Email", "Notes"},
            dialog_fields={"Email": {"invalid": "synthetic"}, "Notes": {"updated": "updated text"}},
        )
        request = {"action": "fill_dialog_field", "label": "Email", "parameter": "invalid"}
        for invalid in (
            {**request, "label": "email"}, {**request, "parameter": "updated"},
            {**request, "value": "raw data"}, {**request, "selector": "input"},
        ):
            self.assertEqual(dispatch(invalid), {"status": "out_of_scope"})
        browser.assert_not_called()

    def test_dialog_field_fill_and_read_expose_only_boolean_matches(self):
        browser = Mock(side_effect=[
            browser_json(False), browser_json({"filled": "native data"}), browser_json(True),
            browser_json(False),
        ])
        fields = {"Notes": {"updated": "synthetic note"}}
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Notes"}, dialog_fields=fields,
        )
        fields["Notes"]["updated"] = "mutated after construction"
        request = {"label": "Notes", "parameter": "updated"}
        self.assertEqual(dispatch({**request, "action": "fill_dialog_field"}), {"status": "ok", "matches": True})
        self.assertEqual(dispatch({**request, "action": "read_dialog_field"}), {"status": "ok", "matches": False})
        before, fill, after, read = [call.args for call in browser.call_args_list]
        self.assertEqual([call[1] for call in (before, fill, after, read)], ["eval", "fill", "eval", "eval"])
        selector = before[2]["selector"]
        self.assertIn('role=textbox[name="Notes"s]', selector)
        self.assertIn('internal:label=', selector)
        self.assertIn('internal:attr=[placeholder=', selector)
        self.assertIn('[role~="dialog"]', json.loads(selector.rsplit("internal:and=", 1)[1]))
        self.assertEqual(fill[2], {"selector": selector, "value": "synthetic note"})
        self.assertEqual(before, after)
        self.assertEqual(after, read)

    def test_dialog_field_fill_does_not_act_without_a_valid_preflight(self):
        browser = Mock(side_effect=[browser_json(None), browser_json({"value": "unexpected data"})])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Email"},
            dialog_fields={"Email": {"invalid": "synthetic"}},
        )
        request = {"action": "fill_dialog_field", "label": "Email", "parameter": "invalid"}
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertEqual(dispatch(request), {"status": "not_actionable"})
        self.assertEqual([call.args[1] for call in browser.call_args_list], ["eval", "eval"])
        browser.side_effect = [browser_json(False), browser_json({}), browser_json("unexpected data")]
        self.assertEqual(dispatch(request), {"status": "unknown_effect"})

    def test_semantic_fields_must_be_observed_unique_and_bound_to_a_parameter(self):
        email = {"role": "textbox", "label": "private", "state": {"visible": True},
                 "field_semantics": ["type:email", "autocomplete:private"]}
        browser = Mock(side_effect=[
            browser_json([email, email]), browser_json([email]), browser_json(False),
            browser_json({"filled": "private"}), browser_json(True), browser_json([]),
        ])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Email", "Notes"},
            dialog_fields={"Email": {"invalid": "synthetic"}, "Notes": {"updated": "synthetic note"}},
            dialog_field_semantics={"type:email": "Email"},
        )
        request = {"action": "fill_dialog_field", "semantic": "type:email", "parameter": "invalid"}
        self.assertEqual(dispatch(request), {"status": "out_of_scope"})
        browser.assert_not_called()
        self.assertTrue(all("field_semantics" not in control for control in dispatch({"action": "observe"})["controls"]))
        self.assertEqual(dispatch(request), {"status": "out_of_scope"})
        control, = dispatch({"action": "observe"})["controls"]
        self.assertEqual(control["field_semantics"], ("type:email",))
        self.assertIsNone(control["label"])
        self.assertEqual(dispatch({**request, "parameter": "updated"}), {"status": "out_of_scope"})
        self.assertEqual(dispatch(request), {"status": "ok", "matches": True})
        preflight, fill, verification = [call.args for call in browser.call_args_list[-3:]]
        self.assertEqual(preflight, verification)
        self.assertEqual(fill[2]["selector"], preflight[2]["selector"])
        self.assertTrue(fill[2]["selector"].startswith('css=input[type="email" i]'))
        self.assertEqual(fill[2]["value"], "synthetic")
        dispatch({"action": "observe"})
        self.assertEqual(dispatch(request), {"status": "out_of_scope"})

    def test_semantic_field_configuration_rejects_unapproved_tokens_or_labels(self):
        for semantics in (
            {"type:password": "Email"}, {"autocomplete:email": "Unbound"},
            {'name:email"] >> button': "Email"}, {"name:": "Email"},
        ):
            with self.subTest(semantics=semantics), self.assertRaises(ValueError):
                make_observe_dispatch(
                    Mock(), tab="owned-tab", allowed_labels={"Email"},
                    dialog_fields={"Email": {"invalid": "synthetic"}},
                    dialog_field_semantics=semantics,
                )

    def test_opt_in_html_name_does_not_export_or_accept_other_names(self):
        browser = Mock(side_effect=[
            browser_json([{"role": "textbox", "state": {"visible": True},
                           "field_semantics": ["name:fullName", "name:private"]}]),
            browser_json(False), browser_json({}), browser_json(True),
        ])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Full name"},
            dialog_fields={"Full name": {"synthetic": "Synthetic full name"}},
            dialog_field_semantics={"name:fullName": "Full name"},
        )
        control, = dispatch({"action": "observe"})["controls"]
        self.assertEqual(control["field_semantics"], ("name:fullName",))
        request = {"action": "fill_dialog_field", "parameter": "synthetic"}
        for token in ("name:private", "name:fullname"):
            self.assertEqual(dispatch({**request, "semantic": token}), {"status": "out_of_scope"})
        self.assertEqual(dispatch({**request, "semantic": "name:fullName"}), {"status": "ok", "matches": True})
        observe_call, preflight, fill, read = [call.args for call in browser.call_args_list]
        self.assertEqual(observe_call[2]["arg"]["semanticSelectors"], {"name:fullName": '[name="fullName"]'})
        self.assertTrue(fill[2]["selector"].startswith('css=[name="fullName"] >> internal:and='))
        self.assertEqual(preflight, read)

    def test_dialog_wait_checks_fresh_observations_and_returns_only_state(self):
        dialog = {"role": "dialog", "label": "private", "state": {"visible": True}}
        browser = Mock(side_effect=[browser_json([dialog]), browser_json([]), browser_json([dialog])])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(), dialog_wait_seconds=1,
        )
        with patch("qabro.observe_tool.sleep") as sleep:
            for state in ("hidden", "visible"):
                self.assertEqual(dispatch({"action": "wait_for_dialog_state", "state": state}),
                                 {"status": "ok", "state": state})
            sleep.assert_called_once()
        self.assertEqual(browser.call_count, 3)

    def test_dialog_wait_denies_worker_deadlines_and_malformed_observations(self):
        browser = Mock(side_effect=[
            browser_json({"private": True}), browser_json([{"role": "dialog"}]),
            TimeoutError("private"),
        ])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(), dialog_wait_seconds=1,
        )
        request = {"action": "wait_for_dialog_state", "state": "hidden"}
        self.assertEqual(dispatch({**request, "timeout": 5}), {"status": "out_of_scope"})
        browser.assert_not_called()
        for status in ("malformed", "malformed", "unavailable"):
            self.assertEqual(dispatch(request), {"status": status})

    def test_dialog_wait_cannot_verify_a_state_after_the_deadline(self):
        browser = Mock(return_value=browser_json([]))
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(), dialog_wait_seconds=1,
        )
        with patch("qabro.observe_tool.monotonic", side_effect=[0, 0.1, 1.1]):
            self.assertEqual(dispatch({"action": "wait_for_dialog_state", "state": "hidden"}),
                             {"status": "timeout"})
        browser.assert_called_once()

    def test_native_dialog_wait_uses_bounded_eval_and_independent_visible_evidence(self):
        dialog = {"role": "dialog", "label": None, "state": {"visible": True}}
        browser = Mock(side_effect=[browser_json("matched"), browser_json([dialog, dialog])])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(),
            dialog_wait_seconds=1, native_dialog_wait=True,
        )
        self.assertEqual(dispatch({"action": "wait_for_dialog_state", "state": "visible"}),
                         {"status": "ok", "state": "visible"})
        hint, observation = [call.args for call in browser.call_args_list]
        self.assertEqual(hint[:2], ("owned-tab", "eval"))
        self.assertEqual(hint[2]["arg"], {"visible": True, "milliseconds": 750})
        self.assertLess(hint[2]["timeout"], 1000)
        self.assertIn(observation[2]["expression"], hint[2]["expression"])

    def test_native_dialog_hint_cannot_verify_hidden_without_valid_observation(self):
        browser = Mock(side_effect=[browser_json("matched"), browser_json({"private": "response"})])
        dispatch = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(),
            dialog_wait_seconds=1, native_dialog_wait=True,
        )
        self.assertEqual(dispatch({"action": "wait_for_dialog_state", "state": "hidden"}),
                         {"status": "malformed"})

    def test_dialog_kind_observation_hides_native_messages_and_buckets_visible_dom_dialogs(self):
        visible = {"role": "dialog", "label": "private title", "state": {"visible": True}}
        browser = Mock(side_effect=[
            browser_json({"dialog": {"type": "confirm", "message": "private prompt"}}),
            browser_json({"dialog": None}), browser_json([visible, visible]),
            browser_json({"dialog": {"type": "private data"}}),
            browser_json({"dialog": None}), browser_json({"unexpected": "private data"}),
        ])
        dispatch = make_observe_dispatch(browser, tab="owned-tab", allowed_labels=set())
        request = {"action": "observe_dialog_kinds"}
        self.assertEqual(dispatch({**request, "auto": "accept"})["status"], "out_of_scope")
        self.assertEqual(dispatch(request), {
            "status": "ok", "native_pending": True, "visible_dom_dialogs": "unverified",
        })
        browser.assert_called_once_with("owned-tab", "dialog", {"action": "status"})
        self.assertEqual(dispatch(request), {
            "status": "ok", "native_pending": False, "visible_dom_dialogs": "multiple",
        })
        self.assertEqual(dispatch(request), {"status": "malformed"})
        self.assertEqual(dispatch(request), {"status": "malformed", "native_pending": False})

    def test_worker_cannot_choose_expression_selector_or_tab(self):
        browser = Mock()
        observe = make_observe_dispatch(browser, tab="owned-tab", allowed_labels={"Save"})
        for key in ("expression", "selector", "tab", "arg"):
            with self.subTest(key=key):
                self.assertEqual(
                    observe({"action": "observe", key: "worker value"}),
                    {"status": "out_of_scope", "controls": ()},
                )
        browser.assert_not_called()

    def test_model_receives_only_filtered_structure(self):
        browser = Mock(return_value={"content": [{"type": "text", "text": json.dumps([
            {"role": "button", "label": "Save", "state": {"disabled": False}},
            {"role": "textbox", "label": "unapproved name"},
        ])}]})
        vocabulary = {"Save"}
        observe = make_observe_dispatch(browser, tab="owned-tab", allowed_labels=vocabulary)
        vocabulary.add("unapproved name")

        response = observe({"action": "observe"})

        self.assertEqual(response, {"status": "ok", "controls": (
            {"role": "button", "label": "Save", "state": {"disabled": False}},
            {"role": "textbox", "label": None, "state": {}},
        )})
        tab, tool, args = browser.call_args.args
        self.assertEqual((tab, tool, args["world"], args["arg"]), ("owned-tab", "eval", "isolated", ["Save"]))
        self.assertIn("querySelectorAll", args["expression"])

    def test_native_errors_and_malformed_results_do_not_reach_model(self):
        browser = Mock()
        observe = make_observe_dispatch(browser, tab="owned-tab", allowed_labels=set())
        browser.side_effect = [
            TimeoutError("private response"), {"isError": True, "content": ["private response"]},
            {"content": [{"type": "text", "text": "private response"}]},
        ]
        for status in ("unavailable", "unavailable", "malformed"):
            self.assertEqual(observe({"action": "observe"}), {"status": status, "controls": ()})

    def test_button_click_denies_by_default_and_rejects_worker_scope(self):
        browser = Mock()
        observe = make_observe_dispatch(browser, tab="owned-tab", allowed_labels={"Open form"})
        self.assertEqual(observe({"action": "click", "label": "Open form"}), {"status": "out_of_scope"})
        observe = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Open form"}, clickable_labels={"Open form"},
        )
        for extra in ("selector", "tab", "force"):
            self.assertEqual(
                observe({"action": "click", "label": "Open form", extra: True})["status"],
                "out_of_scope",
            )
        browser.assert_not_called()

    def test_exact_button_predicate_is_checked_then_reresolved_natively(self):
        browser = Mock(side_effect=[browser_json(True), browser_json({"clicked": "native result"})])
        observe = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Open form"}, clickable_labels={"Open form"},
        )
        self.assertEqual(observe({"action": "click", "label": "Open form"}), {"status": "dispatched"})
        (tab, tool, preflight), (click_tab, click_tool, click) = [call.args for call in browser.call_args_list]
        self.assertEqual((tab, tool, click_tab, click_tool), ("owned-tab", "eval", "owned-tab", "click"))
        self.assertEqual(click, {"selector": preflight["selector"]})
        self.assertTrue(click["selector"].startswith('role=button[name="Open form"s] >> internal:and='))
        self.assertIn('[role~=', click["selector"])
        self.assertIn('form button:not', click["selector"])
        self.assertNotIn("nth=", click["selector"])

    def test_preflight_failure_does_not_click_and_click_failure_is_indeterminate(self):
        browser = Mock()
        observe = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels={"Open form"}, clickable_labels={"Open form"},
        )
        request = {"action": "click", "label": "Open form"}
        for rejected in (browser_json(False), {"isError": True, "content": ["ambiguous private targets"]}):
            browser.reset_mock()
            browser.return_value = rejected
            self.assertEqual(observe(request), {"status": "not_actionable"})
            browser.assert_called_once()
        browser.side_effect = [browser_json(True), TimeoutError("private response")]
        self.assertEqual(observe(request), {"status": "unknown_effect"})

    def test_owned_rows_require_host_identity_and_reject_worker_queries(self):
        browser = Mock()
        observe = make_observe_dispatch(browser, tab="owned-tab", allowed_labels=set())
        self.assertEqual(observe({"action": "observe_owned_rows"}), {"status": "out_of_scope"})
        observe = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(), owned_identity=("owned key",),
        )
        self.assertEqual(
            observe({"action": "observe_owned_rows", "query": "worker key"})["status"],
            "out_of_scope",
        )
        browser.assert_not_called()

    def test_owned_row_reply_exposes_only_the_visible_count_bucket(self):
        browser = Mock(side_effect=[
            browser_json("none"), browser_json("one"), browser_json("multiple"),
            browser_json({"rows": ["private response"]}), browser_json("private response"),
            {"isError": True, "content": ["private response"]},
        ])
        observe = make_observe_dispatch(
            browser, tab="owned-tab", allowed_labels=set(),
            owned_identity=("owned name", "owned identifier"),
        )
        for bucket in ("none", "one", "multiple"):
            self.assertEqual(
                observe({"action": "observe_owned_rows"}), {"status": "ok", "visible_matches": bucket},
            )
            tab, tool, args = browser.call_args.args
            self.assertEqual((tab, tool, args["world"]), ("owned-tab", "eval", "isolated"))
            self.assertEqual(args["arg"], ["owned name", "owned identifier"])
        for status in ("malformed", "malformed", "unavailable"):
            self.assertEqual(observe({"action": "observe_owned_rows"}), {"status": status})
