import unittest
from unittest.mock import Mock

from qabro.dispatch_batch import BatchAction, DraftField, make_batched_tool
from qabro.observe_tool import OBSERVE_DIALOG_FIELDS_TOOL


BASE_TOOL = {
    "name": "browser_observe",
    "description": "Observe or use approved controls.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"enum": ["observe", "click", "read_dialog_field", "fill_dialog_field"]},
            "label": {"type": "string"},
            "parameter": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}
OBSERVE = {"action": "observe"}
CLICK = {"action": "click", "label": "Add User"}
READ = {"action": "read_dialog_field", "label": "Notes", "parameter": "expected"}
FILL = {**READ, "action": "fill_dialog_field"}


def ok(result):
    return result["status"] == "ok"


def matches(result):
    return ok(result) and result.get("matches") is True


class DispatchBatchTests(unittest.TestCase):
    def draft_dispatch(self, guard):
        return make_batched_tool(guard, BASE_TOOL, {
            "fill_dialog_field": BatchAction(
                frozenset({"label", "parameter"}), lambda _: True, mutates=True,
                draft_grants={
                    ("Notes", "expected"): DraftField("local-form", "notes"),
                    ("Notes", "alternate"): DraftField("local-form", "notes"),
                    ("Name", "expected"): DraftField("local-form", "name"),
                    ("Other", "expected"): DraftField("another-form", "other"),
                },
            ),
            "click": BatchAction(frozenset({"label"}), lambda _: True, mutates=True),
            "observe": BatchAction(frozenset(), ok),
        })[1]

    def test_distinct_draft_fields_preserve_order_and_individual_equality(self):
        name = {**FILL, "label": "Name"}
        answer = {"status": "ok", "matches": True}
        guard = Mock(side_effect=[answer, answer, {"status": "ok"}])
        result = self.draft_dispatch(guard)({"action": "batch", "steps": [FILL, name, OBSERVE]})
        self.assertEqual(result, {"status": "complete", "trace": [
            {"request": FILL, "result": answer},
            {"request": name, "result": answer},
            {"request": OBSERVE, "result": {"status": "ok"}},
        ]})
        self.assertEqual([call.args[0] for call in guard.call_args_list], [FILL, name, OBSERVE])

    def test_bad_draft_plans_never_begin_dispatch(self):
        guard = Mock()
        dispatch = self.draft_dispatch(guard)
        for other in (FILL, {**FILL, "parameter": "alternate"}, {**FILL, "parameter": "ungranted"},
                      {**FILL, "label": "Other"}, CLICK):
            with self.subTest(other=other):
                result = dispatch({"action": "batch", "steps": [OBSERVE, FILL, other]})
                self.assertEqual(result, {"status": "out_of_scope"})
        guard.assert_not_called()

    def test_draft_stops_without_verified_equality_even_with_permissive_policy(self):
        for reply in ({"status": "ok", "matches": False}, {"status": "ok"}, {"status": "dispatched"},
                      {"status": "unknown_effect"}, TimeoutError()):
            guard = Mock(side_effect=[reply])
            result = self.draft_dispatch(guard)({"action": "batch", "steps": [FILL, {**FILL, "label": "Name"}]})
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(len(result["trace"]), 1)
            guard.assert_called_once_with(FILL)

    def test_draft_canonical_identity_collides_across_action_rules(self):
        guard = Mock()
        tool = {**OBSERVE_DIALOG_FIELDS_TOOL}
        schema = tool["inputSchema"]
        properties = schema["properties"]
        tool["inputSchema"] = {**schema, "properties": {
            **properties, "action": {"enum": ["fill_dialog_field", "fill_field_by_semantic"]},
        }}
        field = DraftField("form", "notes")
        _, dispatch = make_batched_tool(guard, tool, {
            "fill_dialog_field": BatchAction(
                frozenset({"label", "parameter"}), matches, True, {("Notes", "expected"): field},
            ),
            "fill_field_by_semantic": BatchAction(
                frozenset({"semantic", "parameter"}), matches, True, {("expected", "type:notes"): field},
            ),
        })
        alias = {"action": "fill_field_by_semantic", "semantic": "type:notes", "parameter": "expected"}
        self.assertEqual(dispatch({"action": "batch", "steps": [FILL, alias]}), {"status": "out_of_scope"})
        guard.assert_not_called()

    def test_observe_fields_schema_batches_only_explicit_semantic_reads(self):
        read = {"action": "read_dialog_field", "semantic": "type:email", "parameter": "expected"}
        guard = Mock(return_value={"status": "ok", "matches": True})
        _, dispatch = make_batched_tool(guard, OBSERVE_DIALOG_FIELDS_TOOL, {
            "read_dialog_field": BatchAction(frozenset({"semantic", "parameter"}), matches),
        })
        self.assertEqual(dispatch({"action": "batch", "steps": [read]})["status"], "complete")
        guard.assert_called_once_with(read)

        guard.reset_mock()
        for rejected in (
            {**read, "action": "fill_dialog_field"},
            {**read, "text": "otherwise valid scalar"},
            {**read, "selector": "input"},
            {**read, "expression": "untrusted JavaScript"},
        ):
            with self.subTest(rejected=rejected):
                self.assertEqual(
                    dispatch({"action": "batch", "steps": [read, rejected]}),
                    {"status": "out_of_scope"},
                )
        guard.assert_not_called()

    def make(self, guard, *, allow_receipt=False):
        def click_receipt(result):
            return allow_receipt and result["status"] == "dispatched"

        return make_batched_tool(guard, BASE_TOOL, {
            "observe": BatchAction(frozenset(), ok),
            "click": BatchAction(frozenset({"label"}), click_receipt, mutates=True),
            "read_dialog_field": BatchAction(frozenset({"label", "parameter"}), matches),
            "fill_dialog_field": BatchAction(frozenset({"label", "parameter"}), matches, mutates=True),
        }, max_steps=3)

    def test_original_dispatch_and_bounded_schema_are_available_without_mutating_base(self):
        guard = Mock(return_value={"status": "ok", "controls": []})
        tool, dispatch = self.make(guard)
        self.assertEqual(dispatch(OBSERVE), {"status": "ok", "controls": []})
        self.assertEqual(guard.call_args.args, (OBSERVE,))
        self.assertEqual(tool["name"], BASE_TOOL["name"])
        alternatives = tool["inputSchema"]["oneOf"]
        self.assertEqual(alternatives[0], BASE_TOOL["inputSchema"])
        nested = alternatives[1]["properties"]["steps"]
        self.assertEqual((nested["minItems"], nested["maxItems"]), (1, 3))
        self.assertEqual(len(nested["items"]["oneOf"]), 4)
        self.assertNotIn("oneOf", BASE_TOOL["inputSchema"])
        self.assertNotIn("steps", BASE_TOOL["inputSchema"]["properties"])

    def test_exported_schema_mutation_cannot_authorize_a_raw_browser_parameter(self):
        guard = Mock()
        tool, dispatch = self.make(guard)
        tool["inputSchema"]["oneOf"][0]["properties"]["selector"] = {"type": "string"}
        self.assertEqual(dispatch({**CLICK, "selector": "#outside"}), {"status": "out_of_scope"})
        guard.assert_not_called()

    def test_rejects_entire_plan_before_dispatch_when_a_step_is_invalid(self):
        guard = Mock()
        _, dispatch = self.make(guard, allow_receipt=True)
        for request in (
            {"action": "batch", "steps": []},
            {"action": "batch", "steps": [OBSERVE] * 4},
            {"action": "batch", "steps": [OBSERVE, CLICK, FILL]},
            {"action": "batch", "steps": [OBSERVE, {**CLICK, "expression": "bad"}]},
            {"action": "batch", "steps": [OBSERVE, {**CLICK, "selector": "#bad"}]},
            {"action": "batch", "steps": [OBSERVE, {**CLICK, "label": {"selector": "#bad"}}]},
            {"action": "batch", "steps": [OBSERVE, {"action": "click"}]},
            {"action": "batch", "steps": [OBSERVE, {"action": "batch", "steps": [CLICK]}]},
            {"action": "batch", "steps": [OBSERVE], "tab": "other"},
            {**CLICK, "selector": "#bad"},
        ):
            with self.subTest(request=request):
                self.assertEqual(dispatch(request), {"status": "out_of_scope"})
        guard.assert_not_called()

    def test_explicit_receipt_policy_continues_without_inventing_pass(self):
        results = [{"status": "ok", "controls": []}, {"status": "dispatched"}, {"status": "ok", "matches": True}]
        guard = Mock(side_effect=results)
        _, dispatch = self.make(guard, allow_receipt=True)
        steps = [OBSERVE, CLICK, READ]
        outcome = dispatch({"action": "batch", "steps": steps})
        self.assertEqual(outcome, {"status": "complete", "trace": [
            {"request": request, "result": result} for request, result in zip(steps, results, strict=True)
        ]})
        self.assertEqual([call.args[0] for call in guard.call_args_list], steps)

    def test_mismatch_or_unaccepted_receipt_stops_in_order(self):
        for outcome, steps in (
            ({"status": "ok", "matches": False}, [READ, OBSERVE]),
            ({"status": "dispatched"}, [CLICK, OBSERVE]),
        ):
            guard = Mock(return_value=outcome)
            _, dispatch = self.make(guard)
            self.assertEqual(dispatch({"action": "batch", "steps": steps}), {
                "status": "stopped", "trace": [{"request": steps[0], "result": outcome}],
            })
            guard.assert_called_once_with(steps[0])

    def test_incomplete_child_evidence_stops_without_losing_its_receipt(self):
        guard = Mock(return_value={"status": "ok"})
        _, dispatch = make_batched_tool(guard, BASE_TOOL, {
            "read_dialog_field": BatchAction(frozenset({"label", "parameter"}), lambda result: result["matches"]),
            "observe": BatchAction(frozenset(), ok),
        })
        self.assertEqual(dispatch({"action": "batch", "steps": [READ, OBSERVE]}), {
            "status": "stopped", "trace": [{"request": READ, "result": {"status": "ok"}}],
        })
        guard.assert_called_once_with(READ)

    def test_unknown_effect_overrides_even_an_explicit_continuation_policy(self):
        for received in ({"status": "unknown_effect"}, TimeoutError("private"), None):
            guard = Mock(side_effect=[received])
            _, dispatch = make_batched_tool(guard, BASE_TOOL, {
                "click": BatchAction(frozenset({"label"}), lambda _: True, mutates=True),
                "observe": BatchAction(frozenset(), lambda _: True),
            })
            outcome = dispatch({"action": "batch", "steps": [CLICK, OBSERVE]})
            self.assertEqual(outcome, {"status": "stopped", "trace": [
                {"request": CLICK, "result": {"status": "unknown_effect"}},
            ]})
            guard.assert_called_once_with(CLICK)
