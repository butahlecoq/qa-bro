import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from qabro.guarded_edit_action import (
    EditBinding, EditDialogReceipt, RoleObservationBinding, make_guarded_edit,
)
from qabro.guarded_form_action import ApprovedFormAction, FormFieldBinding
from qabro.owned_row_action import OwnedRowCell
from qabro.owned_search import OwnedSearchQuery, SearchCompleted


def response(result):
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


class GuardedEditTests(unittest.TestCase):
    def setUp(self):
        identity = ("Synthetic record", "test-account", "user@example.test")
        self.query = OwnedSearchQuery("initial", "All", identity[0], identity[1:])
        self.search = SearchCompleted(self.query, "initial-proof", "host-tab")
        self.fresh = SearchCompleted(replace(self.query, generation="reloaded"), "fresh-proof", "host-tab")
        form = ApprovedFormAction(
            "host-tab", "https://demo.test", None, "Edit record", "Commit",
            tuple(FormFieldBinding(None, value, name, require_editable=False)
                  for name, value in zip(("name", "handle", "address"), identity, strict=True)),
            operation="edit", action_default=False,
        )
        self.binding = EditBinding(
            form, "table", tuple(OwnedRowCell(i, text) for i, text in enumerate(identity, 1)),
            self.search, "Change", FormFieldBinding("access-level", "Standard"),
            FormFieldBinding("active", True), FormFieldBinding("draft", "old note"),
            FormFieldBinding("draft", "new note"),
        )

    def test_requires_native_row_open_original_read_and_new_search_for_readback(self):
        calls = []

        def browser(tab, tool, args):
            self.assertEqual(tab, "host-tab")
            calls.append((tool, args))
            return response(True if tool == "eval" else {"clicked": "private metadata"})

        edit = make_guarded_edit(browser, self.binding)
        self.assertIsNone(edit.read_owned_original())
        self.assertFalse(edit.read_persisted())
        self.assertEqual(edit.save(EditDialogReceipt()).status, "not_actionable")
        self.assertEqual(edit.open_owned().status, "dispatched")
        self.assertEqual(edit.open_owned().status, "already_attempted")
        proof = edit.read_owned_original()
        self.assertIsInstance(proof, EditDialogReceipt)
        self.assertEqual(edit.save(EditDialogReceipt()).status, "not_actionable")
        self.assertEqual(edit.save(proof).status, "dispatched")
        self.assertEqual(edit.save(proof).status, "not_actionable")
        self.assertFalse(edit.read_persisted())
        self.assertEqual(edit.reopen_owned(self.search).status, "not_actionable")
        self.assertEqual(edit.reopen_owned(self.fresh).status, "dispatched")
        self.assertTrue(edit.read_persisted())
        self.assertEqual([tool for tool, _ in calls],
                         ["eval", "click", "eval", "eval", "click", "eval", "click", "eval"])
        form_checks = [args for tool, args in calls if tool == "eval" and isinstance(args.get("arg"), dict)]
        self.assertEqual([a["arg"]["read_only"] for a in form_checks], [True, False, True])
        expected = [[f["expected"] for f in a["arg"]["fields"]] for a in form_checks]
        self.assertEqual(expected[0][-3:], ["Standard", True, "old note"])
        self.assertEqual(expected[1][-3:], ["Standard", True, "new note"])
        self.assertEqual(expected[1], expected[2])
        self.assertEqual(calls[4][1]["selector"], form_checks[1]["selector"])
        self.assertEqual(calls[4][1]["clickCount"], 1)

    def test_failed_or_expired_proof_does_not_click_save(self):
        calls = []

        def browser(_tab, tool, args):
            calls.append(tool)
            if tool == "eval" and isinstance(args.get("arg"), dict) and args["arg"]["fields"][-1]["expected"] == "new note":
                return response(False)
            return response(True if tool == "eval" else {"clicked": "action"})

        edit = make_guarded_edit(browser, self.binding)
        self.assertEqual(edit.open_owned().status, "dispatched")
        proof = edit.read_owned_original()
        self.assertIsNotNone(proof)
        self.assertEqual(edit.save(proof).status, "not_actionable")
        self.assertEqual(calls.count("click"), 1)

        edit = make_guarded_edit(browser, self.binding)
        with patch("qabro.guarded_edit_action.monotonic", side_effect=[0, 1, 2, 91]):
            edit.open_owned()
            self.assertEqual(edit.save(edit.read_owned_original()).status, "not_actionable")
        self.assertEqual(calls.count("click"), 2)

    def test_mismatched_row_search_or_role_binding_fails_closed(self):
        mismatch = SearchCompleted(replace(self.query, marker="other"), "other", "host-tab")
        for binding in (
            replace(self.binding, initial_search=mismatch),
            replace(self.binding, stable_active=FormFieldBinding("active", "Active")),
            replace(self.binding, updated_draft=FormFieldBinding("different-field", "new note")),
        ):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                make_guarded_edit(lambda *_: self.fail("No browser call expected"), binding)


    def test_custom_role_needs_fresh_exact_witness_before_save(self):
        declarations = []
        readings = iter([True, False])
        clicks = []

        def witness(tab, title, expected):
            declarations.append((tab, title, expected))
            return next(readings)

        def browser(_tab, tool, args):
            if tool == "click":
                clicks.append(args["selector"])
            return response(True if tool == "eval" else {"clicked": "action"})

        edit = make_guarded_edit(browser, replace(
            self.binding, stable_role=RoleObservationBinding("Standard", witness),
        ))
        self.assertEqual(edit.open_owned().status, "dispatched")
        proof = edit.read_owned_original()
        self.assertIsNotNone(proof)
        self.assertEqual(edit.save(proof).status, "not_actionable")
        self.assertEqual(edit.save(proof).status, "not_actionable")
        self.assertEqual(declarations, [("host-tab", "Edit record", "Standard")] * 2)
        self.assertEqual(len(clicks), 1)
