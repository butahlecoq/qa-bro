import json
import shutil
import subprocess
import unittest
from dataclasses import replace

from qabro.guarded_form_action import (
    ApprovedFormAction, FormFieldBinding, make_guarded_form_action,
)


def response(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class GuardedFormActionTests(unittest.TestCase):
    def setUp(self):
        self.binding = ApprovedFormAction(
            tab="host-tab", origin="https://demo.test", dialog_id='active"dialog',
            title='Create "item"', action="Commit",
            fields=(FormFieldBinding("notes", "synthetic detail"), FormFieldBinding("toggle", False)),
            action_focused=False, action_default=True,
        )

    def test_preflight_precedes_strict_single_native_click(self):
        calls = []

        def browser(tab, tool, args):
            self.assertEqual(tab, "host-tab")
            calls.append((tool, args))
            return response(True if tool == "eval" else {"clicked": "Commit", "url": "private"})

        run = make_guarded_form_action(browser, self.binding)
        self.assertEqual(run().status, "dispatched")
        self.assertEqual(run().status, "already_attempted")
        self.assertEqual([tool for tool, _ in calls], ["eval", "click"])
        _, guard = calls[0]
        _, click = calls[1]
        self.assertEqual(guard["world"], "isolated")
        self.assertEqual(guard["selector"], click["selector"])
        self.assertEqual(click["clickCount"], 1)
        self.assertIn("internal:has=", click["selector"])
        self.assertIn('role=button[name="Commit"s]', click["selector"])
        self.assertIn(":not(:focus):default", click["selector"])
        self.assertEqual(guard["arg"]["fields"][0]["expected"], "synthetic detail")
        self.assertNotIn("synthetic detail", guard["expression"])
        self.assertNotIn("synthetic detail", click["selector"])

    def test_refuses_false_or_malformed_preflight(self):
        for result in (False, "true", {"matches": True}, None):
            with self.subTest(result=result):
                def browser(_tab, tool, _args):
                    self.assertEqual(tool, "eval")
                    return response(result)

                run = make_guarded_form_action(browser, self.binding)
                self.assertEqual(run().status, "not_actionable")

    def test_unknown_click_effect_is_terminal_for_this_dispatch(self):
        calls = []

        def browser(_tab, tool, _args):
            calls.append(tool)
            if tool == "click":
                raise TimeoutError("Possibly dispatched")
            return response(True)

        run = make_guarded_form_action(browser, self.binding)
        self.assertEqual(run().status, "unknown_effect")
        self.assertEqual(run().status, "already_attempted")
        self.assertEqual(calls, ["eval", "click"])

    def test_edit_and_invalid_bindings_fail_closed(self):
        def browser(*_):
            self.fail("Unsupported binding must not resolve or act")

        for binding in (
            replace(self.binding, operation="edit"),
            replace(self.binding, fields=()),
            replace(self.binding, fields=self.binding.fields * 2),
            replace(self.binding, action_default=1),
            replace(self.binding, allow_body_focus=1),
            replace(self.binding, fields=(FormFieldBinding("notes", "value", html_name="notes"),)),
            replace(self.binding, fields=(FormFieldBinding(None, "value"),)),
            replace(self.binding, fields=(FormFieldBinding(None, "12", html_name="n", child_input_role="spinbutton"),)),
            replace(self.binding, fields=(FormFieldBinding("wrapper", "12", child_input_role="textbox"),)),
            replace(self.binding, fields=(FormFieldBinding("notes", 1234),)),
            replace(self.binding, fields=(FormFieldBinding("wrapper", 12.34, child_input_role="spinbutton"),)),
            replace(self.binding, fields=(FormFieldBinding("wrapper", -1, child_input_role="spinbutton"),)),
        ):
            with self.subTest(binding=binding):
                self.assertEqual(make_guarded_form_action(browser, binding)().status, "unsupported_binding")

    @unittest.skipUnless(shutil.which("node"), "Node is needed to run the preflight")
    def test_approved_spinbutton_wrapper_requires_one_direct_visible_native_input(self):
        binding = replace(self.binding, dialog_id=None, action_focused=None, action_default=None,
                          fields=(FormFieldBinding("price-wrapper", "$12.34", child_input_role="spinbutton"),))
        script = r"""
        const [expression, binding] = JSON.parse(process.argv[1]);
        const check = eval(expression);
        global.CSS = {escape: value => value};
        global.getComputedStyle = () => ({visibility:'visible'});
        const common = {
            getClientRects() {return this.hidden ? [] : [0]},
            closest(query) {return query.startsWith('dialog') ? dialog : null},
            getAttribute(name) {return this[name] ?? null},
            hasAttribute() {return false}, matches() {return false},
        };
        const heading = {...common, innerText:binding.title};
        const field = {...common, localName:'input', role:'spinbutton', type:'text', value:'$12.34'};
        const wrapper = {...common, children:[field]};
        const dialog = {...common, contains: el=>el===field, querySelectorAll:()=>[heading]};
        const doc = {location:{origin:binding.origin},activeElement:field,
            querySelectorAll: query => query.startsWith('#') ? [wrapper] : [dialog]};
        const button = {...common, localName:'button', isConnected:true, innerText:binding.action, ownerDocument:doc};
        const results=[check(button,binding)];
        wrapper.children.push({...field});
        results.push(check(button,binding));
        wrapper.children=[{...field,hidden:true}];
        results.push(check(button,binding));
        wrapper.children=[{...common, localName:'div',children:[field]}];
        results.push(check(button,binding));
        wrapper.children=[{...field,value:'$12.35'}];
        results.push(check(button,binding));
        const numeric = {...binding, fields:[{...binding.fields[0],expected:123456}]};
        for (const sample of ['$1,234.56','1234.56','1234.560','1234.57','$12,34.56','1234.56\n','1234.56 USD']) {
            wrapper.children=[{...field,value:sample}];
            results.push(check(button,numeric));
        }
        for (const sample of ['$12.30','12.3','12.03']) {
            wrapper.children=[{...field,value:sample}];
            results.push(check(button,{...numeric,fields:[{...numeric.fields[0],expected:1230}]}));
        }
        console.log(JSON.stringify(results));
        """

        def browser(_tab, tool, args):
            if tool == "click":
                return response({"clicked": "Commit"})
            probe = subprocess.run(["node", "-e", script, json.dumps([args["expression"], args["arg"]])],
                                   capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr[-1000:])
            self.assertEqual(json.loads(probe.stdout),
                             [True, False, False, False, False,
                              True, True, False, False, False, False, False,
                              True, True, False])
            return response(True)

        self.assertEqual(make_guarded_form_action(browser, binding)().status, "dispatched")

    @unittest.skipUnless(shutil.which("node"), "Node is needed to run the preflight")
    def test_name_binding_rechecks_unique_dialog_and_native_fields_without_ids(self):
        binding = replace(
            self.binding, dialog_id=None, action_focused=None, action_default=None,
            fields=(FormFieldBinding(None, "draft text", html_name="notes"),
                    FormFieldBinding(None, False, html_name="active")),
        )
        source = """
        const [expression, binding] = JSON.parse(process.argv[1]);
        const preflight = eval(expression);
        global.getComputedStyle = () => ({visibility: 'visible'});
        let duplicateDialog = false;
        let duplicateField = false;
        const scope = {
            getClientRects: () => [0], closest: () => null, getAttribute: () => null,
            contains: el => el === notes,
            querySelectorAll: query => query.startsWith('h1') ? [heading] :
                duplicateField ? [notes, toggle, {...notes}] : [notes, toggle],
        };
        const node = {
            getClientRects: () => [0], closest: query => query.startsWith('dialog') ? scope : null,
            getAttribute: () => null, hasAttribute: () => false, matches: () => false,
        };
        const heading = {...node, innerText: binding.title};
        const notes = {...node, localName: 'textarea', name: 'notes', value: 'draft text'};
        const toggle = {...node, localName: 'input', type: 'checkbox', name: 'active', checked: false};
        const secondary = {...node, querySelectorAll: () => []};
        const doc = {
            location: {origin: binding.origin}, activeElement: notes,
            body: {},
            querySelectorAll: () => duplicateDialog ? [scope, scope] : [scope],
        };
        const action = {...node, isConnected: true, ownerDocument: doc, localName: 'button', innerText: binding.action};
        const results = [preflight(action, binding)];
        duplicateDialog = true;
        results.push(preflight(action, binding));
        duplicateDialog = false;
        duplicateField = true;
        results.push(preflight(action, binding));
        duplicateField = false;
        notes.value = 'changed';
        results.push(preflight(action, binding));
        notes.value = 'draft text';
        doc.activeElement = doc.body;
        results.push(preflight(action, binding));
        const allowed = {...binding, allow_body_focus: true};
        results.push(preflight(action, allowed));
        doc.activeElement = {};
        results.push(preflight(action, allowed));
        doc.activeElement = doc.body;
        doc.querySelectorAll = () => [scope, secondary];
        results.push(preflight(action, allowed));
        doc.querySelectorAll = () => [scope];
        results.push(preflight(action, {...allowed, operation: 'edit'}));
        process.stdout.write(JSON.stringify(results));
        """
        calls = []

        def browser(_tab, tool, args):
            calls.append((tool, args))
            if tool == "click":
                return response({"clicked": "Commit"})
            result = subprocess.run(
                ["node", "-e", source, json.dumps([args["expression"], args["arg"]])],
                capture_output=True, check=True, text=True, timeout=5,
            )
            statuses = json.loads(result.stdout)
            self.assertEqual(statuses, [True, False, False, False, False, True, False, False, False])
            return response(statuses[0])

        self.assertEqual(make_guarded_form_action(browser, binding)().status, "dispatched")
        self.assertEqual([tool for tool, _ in calls], ["eval", "click"])
        selector = calls[1][1]["selector"]
        self.assertEqual(selector, calls[0][1]["selector"])
        self.assertIn("internal:has-not=", selector)
        self.assertNotIn("[id=", selector)
        self.assertNotIn("draft text", selector)


    @unittest.skipUnless(shutil.which("node"), "Node is needed to run the preflight")
    def test_preflight_projection_rejects_changed_fields_and_inactive_scope(self):
        source = """
        const [expression, binding] = JSON.parse(process.argv[1]);
        const preflight = eval(expression);
        global.CSS = {escape: value => value};
        global.getComputedStyle = () => ({visibility: 'visible'});
        const scope = {
            getClientRects: () => [0], closest: () => null,
            getAttribute: () => 'title', contains: el => el === notes,
        };
        const node = {
            getClientRects: () => [0],
            closest: selector => selector.startsWith('dialog') ? scope : null,
            getAttribute: () => null,
            hasAttribute: () => false,
            matches: () => false,
        };
        const title = {...node, innerText: binding.title};
        const notes = {...node, localName: 'textarea', value: binding.fields[0].expected};
        const toggle = {...node, localName: 'input', type: 'checkbox', checked: false};
        const ids = {[binding.dialog_id]: scope, title, notes, toggle};
        const doc = {
            location: {origin: binding.origin},
            activeElement: notes,
            querySelectorAll: key => key.startsWith('#') ? [ids[key.slice(1)]] : [scope],
        };
        const action = {
            ...node, isConnected: true, ownerDocument: doc, localName: 'button',
            innerText: binding.action, matches: selector => selector === ':default',
        };
        const results = [preflight(action, binding)];
        notes.value += ' changed';
        results.push(preflight(action, binding));
        notes.value = binding.fields[0].expected;
        doc.activeElement = {};
        results.push(preflight(action, binding));
        doc.activeElement = notes;
        toggle.checked = true;
        results.push(preflight(action, binding));
        toggle.checked = false;
        action.matches = () => false;
        results.push(preflight(action, binding));
        process.stdout.write(JSON.stringify(results));
        """

        def browser(_tab, tool, args):
            if tool == "click":
                return response({"clicked": "Commit"})
            result = subprocess.run(
                ["node", "-e", source, json.dumps([args["expression"], args["arg"]])],
                capture_output=True, check=True, text=True, timeout=5,
            )
            statuses = json.loads(result.stdout)
            self.assertEqual(statuses, [True, False, False, False, False])
            return response(statuses[0])

        self.assertEqual(make_guarded_form_action(browser, self.binding)().status, "dispatched")
