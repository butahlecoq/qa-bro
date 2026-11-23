import json
import shutil
import subprocess
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from qabro.evidence_query import (
    ApprovedQueryScope, compile_evidence_query, mint_verified_field, observe_evidence_query,
)


def proposal():
    return {
        "status": "CANDIDATE_UNVALIDATED",
        "inputs": {
            "scope": {"type": "dynamic_scope_handle"},
            "label": {"type": "text"},
            "role": {"type": "optional_role_matcher"},
            "expected": {"type": "optional_typed_value"},
        },
        "predicates": [{"type": name} for name in (
            "unique_current_label_in_scope", "nonempty_explicit_html_link",
            "unique_in_scope_noneditable_linked_wrapper",
            "unique_visible_enabled_editable_descendant_matching_role_when_given",
        )],
        "scan_budget": {"type": "finite", "max_candidates": 100},
        "abort_on": ["ambiguity", "missing_link", "stale_scope", "budget_exhaustion"],
        "output": {
            "mode": "read_only",
            "handle": "ephemeral",
            "match_result": "unique_match_or_no_match",
            "value": {
                "type": "optional_typed_observation",
                "independent_when_expected_requested": True,
                "equality": "typed",
                "never_asserted_by_discovery": True,
            },
        },
        "runtime_safety_policies": {"type": "prospective_guards", "are_observations": False},
        "provenance": ["a" * 64],
    }


class EvidenceQueryTests(unittest.TestCase):
    def setUp(self):
        self.query = compile_evidence_query(proposal())
        self.scope = ApprovedQueryScope(
            "tab", "https://demo.test", "dialog[open]", 'Total "amount"', "spinbutton",
        )

    def test_rejects_unsupported_operators_and_malformed_budgets(self):
        modifications = (
            ("selector", "body"),
            ("predicates", [{"type": "run_javascript", "code": "void 0"}]),
            ("scan_budget", {"type": "finite", "max_candidates": True}),
            ("scan_budget", {"type": "finite", "max_candidates": 101}),
            ("provenance", ["raw data"]),
        )
        for key, value in modifications:
            with self.subTest(key=key, value=value):
                candidate = {**proposal(), key: value}
                with self.assertRaises(ValueError):
                    compile_evidence_query(candidate)
        for key in ("never_asserted_by_discovery", "independent_when_expected_requested"):
            candidate = deepcopy(proposal())
            candidate["output"]["value"][key] = 1
            with self.assertRaises(ValueError):
                compile_evidence_query(candidate)

    def test_runtime_uses_only_host_bound_scope_and_returns_one_status(self):
        def browser(tab, tool, args):
            self.assertEqual((tab, tool), ("tab", "eval"))
            self.assertEqual(args["world"], "isolated")
            self.assertEqual(args["selector"], "dialog[open]")
            self.assertEqual(args["arg"], {
                "origin": "https://demo.test", "label": 'Total "amount"',
                "role": "spinbutton", "budget": 100,
            })
            self.assertNotIn(self.scope.label, args["expression"])
            return {"content": [{"type": "text", "text": "unique_match"}]}

        self.assertEqual(observe_evidence_query(browser, self.query, self.scope).status, "unique_match")

    def test_value_observation_and_unapproved_scope_do_not_call_browser(self):
        def browser(*_):
            self.fail("Expected to stop before opening a browser observation")

        result = observe_evidence_query(browser, self.query, self.scope, expected=0)
        self.assertEqual(result.status, "value_observation_unsupported")
        self.assertEqual(observe_evidence_query(browser, self.query, None).status, "stale_scope")

    def test_runtime_drops_arbitrary_values(self):
        def browser(*_):
            return {"content": [{"type": "text", "text": 'private customer value'}]}

        self.assertEqual(observe_evidence_query(browser, self.query, self.scope).status, "read_failed")

    @unittest.skipUnless(shutil.which("node"), "Node is needed to run the read-only DOM projection")
    def test_runs_projection_on_a_minimal_dom_fixture(self):
        fixture = """
        const [project, args] = JSON.parse(process.argv[1]);
        const run = eval(project);
        global.NodeFilter = {SHOW_ELEMENT: 1};
        global.CSS = {escape: text => text};
        global.getComputedStyle = () => ({visibility: 'visible'});

        const input = {
            id: 'control', localName: 'input', type: 'number', hidden: false,
            getClientRects() {return this.hidden ? [] : [0]}, closest: () => null,
            matches: () => false, hasAttribute: () => false,
        };
        const wrapper = {...input, id: 'wrapped', localName: 'div', contains: el => el === input};
        const label = {...input, localName: 'label', htmlFor: wrapper.id, innerText: args.label};
        let elements = [label, wrapper, input];
        let duplicate = false;
        const scope = {
            ...wrapper, isConnected: true,
            ownerDocument: {
                location: {origin: args.origin},
                createTreeWalker() {
                    let index = 0;
                    return {nextNode: () => elements[index++]};
                },
                getElementById: id => elements.find(el => el.id === id),
                querySelectorAll: selector => selector === '#wrapped' ?
                    (duplicate ? [wrapper, {...wrapper}] : [wrapper]) : [input],
            },
        };
        const results = [
            run(scope, args),
            run(scope, {...args, captureIdentity: true}),
            run(scope, {...args, role: 'textbox'}),
            run(scope, {...args, budget: 2}),
        ];
        input.hidden = true;
        results.push(run(scope, args));
        input.hidden = false;
        duplicate = true;
        results.push(run(scope, args));
        duplicate = false;
        elements = [label, {...label}, wrapper, input];
        results.push(run(scope, args));
        scope.isConnected = false;
        results.push(run(scope, args));
        process.stdout.write(JSON.stringify(results));
        """

        def browser(_tab, _tool, args):
            result = subprocess.run(
                ["node", "-e", fixture, json.dumps([args["expression"], args["arg"]])],
                capture_output=True, check=True, text=True, timeout=5,
            )
            values = json.loads(result.stdout)
            self.assertEqual(values, [
                "unique_match",
                {"status": "unique_match", "wrapper": "wrapped", "field": "control",
                 "tag": "input", "type": "number", "role": "spinbutton"},
                "no_match", "budget_exhausted", "no_match", "ambiguous", "ambiguous", "stale_scope",
            ])
            return {"content": [{"type": "text", "text": values[0]}]}

        self.assertEqual(observe_evidence_query(browser, self.query, self.scope).status, "unique_match")


    def test_handle_reresolves_the_same_binding_once(self):
        scope = replace(self.scope, generation="dialog-1")
        payload = {"status": "unique_match", "wrapper": "total", "field": "amount",
                   "tag": "input", "type": "number", "role": "spinbutton"}
        calls = []

        def browser(tab, tool, args):
            calls.append((tab, tool))
            self.assertTrue(args["arg"]["captureIdentity"])
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}

        def apply(tab, selector):
            calls.append((tab, "action"))
            self.assertTrue(selector.startswith('dialog[open] >> css=[id="total"] input[id="amount"]'))
            self.assertIn('role=spinbutton', selector)

        evidence, handle = mint_verified_field(browser, self.query, scope)
        self.assertEqual(evidence.status, "unique_match")
        self.assertFalse(handle(replace(scope), apply))
        self.assertTrue(handle(scope, apply))
        self.assertFalse(handle(scope, apply))
        self.assertEqual(calls, [("tab", "eval"), ("tab", "eval"), ("tab", "action")])

    def test_handle_stops_on_changed_relationship_or_expiry(self):
        scope = replace(self.scope, generation="dialog-1")
        payload = {"status": "unique_match", "wrapper": "total", "field": "amount",
                   "tag": "input", "type": "number", "role": "spinbutton"}

        def browser(*_):
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}

        def apply(*_):
            self.fail("A changed or expired handle cannot reach the action")

        _, handle = mint_verified_field(browser, self.query, scope)
        payload["wrapper"] = "other"
        self.assertFalse(handle(scope, apply))
        payload["wrapper"] = "total"
        self.assertFalse(handle(scope, apply))
        with patch("qabro.evidence_query.monotonic", side_effect=[0, 9]):
            _, handle = mint_verified_field(browser, self.query, scope)
            self.assertFalse(handle(scope, apply))

    def test_compound_match_without_native_identity_does_not_mint_handle(self):
        scope = replace(self.scope, generation="dialog-1")

        def browser(*_):
            return {"content": [{"type": "text", "text": "unique_match"}]}

        evidence, handle = mint_verified_field(browser, self.query, scope)
        self.assertEqual(evidence.status, "unique_match")
        self.assertIsNone(handle)
