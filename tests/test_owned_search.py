import json
import shutil
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import Mock

from qabro.owned_search import (
    OwnedSearchQuery,
    SearchBindings,
    SearchCompleted,
    SearchLifecycleSample,
    admit_search_completion,
    observe_owned_search,
)
from qabro.owned_row_action import OwnedRowCell


def browser_json(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class OwnedSearchTests(unittest.TestCase):
    bindings = SearchBindings('input[role="searchbox"]', '[role="tab"]', '[role="table"]')
    query = OwnedSearchQuery("reload-1/query-2", "Active", "Synthetic marker", ("own-handle", "own@example.test"))

    def observe(self, raw, completed=None):
        browser = Mock(return_value=raw)
        result = observe_owned_search(browser, "assigned-tab", self.bindings, self.query, completed=completed)
        return result, browser

    def test_visible_zero_requires_a_matching_positive_witness(self):
        payload = browser_json({"scope": True, "marker_count": 0, "identity_matches": []})
        partial, browser = self.observe(payload)
        self.assertEqual((partial.status, partial.match, partial.proves_empty), ("partial", "none", False))
        tab, tool, arguments = browser.call_args.args
        self.assertEqual((tab, tool, arguments["world"]), ("assigned-tab", "eval", "isolated"))
        self.assertEqual(arguments["arg"]["marker"], self.query.marker)
        self.assertEqual(arguments["arg"]["identity"], list(self.query.identity))
        self.assertNotIn(self.query.marker, arguments["expression"])

        seen = SearchCompleted(self.query, "observed-query-settled", "assigned-tab")
        found, _ = self.observe(payload, seen)
        self.assertEqual((found.status, found.match, found.proves_empty), ("complete", "none", True))
        self.assertEqual(found.completion_ref, seen.evidence_ref)

    def test_a_witness_for_another_generation_filter_or_marker_is_stale(self):
        result = browser_json({"scope": True, "marker_count": 0, "identity_matches": []})
        other_queries = (
            OwnedSearchQuery("reload-0/query-2", "Active", self.query.marker, self.query.identity),
            OwnedSearchQuery(self.query.generation, "Inactive", self.query.marker, self.query.identity),
            OwnedSearchQuery(self.query.generation, "Active", "Different marker", self.query.identity),
        )
        for query in other_queries:
            with self.subTest(query=query):
                observation, _ = self.observe(result, SearchCompleted(query, "settled", "assigned-tab"))
                self.assertEqual(observation.status, "partial")
                self.assertFalse(observation.proves_empty)

    def test_a_witness_cannot_cross_tabs(self):
        payload = browser_json({"scope": True, "marker_count": 0, "identity_matches": []})
        observation, _ = self.observe(payload, SearchCompleted(self.query, "settled", "different-tab"))
        self.assertEqual(observation.status, "partial")
        self.assertFalse(observation.proves_empty)

    def test_marker_first_distinguishes_conflicting_identity_and_duplicates(self):
        completed = SearchCompleted(self.query, "settled", "assigned-tab")
        for count, matches, expected in (
            (1, [True, True], "owned"),
            (1, [True, False], "conflict"),
            (2, [], "multiple"),
        ):
            with self.subTest(expected=expected):
                result, _ = self.observe(
                    browser_json({"scope": True, "marker_count": count, "identity_matches": matches}),
                    completed,
                )
                self.assertEqual((result.status, result.match, result.proves_empty), ("complete", expected, False))
                self.assertEqual(result.identity_matches, tuple(matches))

    def test_scope_failure_and_unapproved_reply_fields_fail_closed(self):
        completed = SearchCompleted(self.query, "settled", "assigned-tab")
        for raw in (
            {"isError": True, "content": []},
            browser_json({"scope": False, "marker_count": 0, "identity_matches": []}),
            browser_json({"scope": True, "marker_count": 0, "identity_matches": [], "unrelated": "private"}),
            browser_json({"scope": True, "marker_count": True, "identity_matches": []}),
            browser_json({"scope": True, "marker_count": 1, "identity_matches": [True]}),
            browser_json({"scope": True, "marker_count": 1, "identity_matches": [True, 1]}),
        ):
            with self.subTest(raw=raw):
                result, _ = self.observe(raw, completed)
                self.assertEqual((result.status, result.match, result.proves_empty), ("read_failed", None, False))
                self.assertIsNone(result.completion_ref)

    def test_transport_failure_cannot_be_released_as_absence(self):
        browser = Mock(side_effect=TimeoutError("private"))
        result = observe_owned_search(
            browser, "assigned-tab", self.bindings, self.query,
            completed=SearchCompleted(self.query, "settled", "assigned-tab"),
        )
        self.assertEqual(result.status, "read_failed")
        self.assertFalse(result.proves_empty)

    @unittest.skipUnless(shutil.which("node"), "Node is needed to run the read-only DOM projection")
    def test_live_projection_contract_for_direct_text_and_identity_conflicts(self):
        cells = (
            OwnedRowCell(1, self.query.marker, "div.name"),
            OwnedRowCell(3, self.query.identity[0]),
            OwnedRowCell(2, self.query.identity[1]),
        )
        fixture = r"""
        const [project, args, mode] = JSON.parse(process.argv[1]);
        global.getComputedStyle = () => ({visibility:'visible'});
        const node = (tag, entries = {}) => ({
            tagName: tag.toUpperCase(), children: [], childNodes: [],
            get childElementCount() { return this.children.length; },
            getClientRects() { return this.hidden ? [] : [0]; },
            closest() {return null;},
            matches(selector) { return selector.includes(tag); },
            getAttribute(name) { return this[name]; },
            querySelectorAll() { return []; }, querySelector() {return null;},
            ...entries
        });
        const wrapper = () => node('div', {hidden:mode==='hidden', childNodes: [
            {nodeType:1, textContent:'avatar letters'},
            {nodeType:3, nodeValue:'   '+args.marker.replace(' ', '    ')+'  '},
        ]});
        const table = node('table');
        const row = () => {
            const marked = node('td', {children:[wrapper()]});
            if (mode==='ambiguous') marked.children.push(wrapper());
            const email = node('td', {textContent:args.identity[1]});
            const username = node('td', {textContent:args.identity[0]});
            return node('tr', {
                parentElement:table,
                closest(selector) {return selector.startsWith('table,') ? table : null;},
                children: mode==='wrong-column' ? [email, marked, username] : [marked, email, username],
            });
        };
        const rows = [row()];
        if (mode==='duplicate') rows.push(row());
        table.querySelectorAll=() => rows;
        global.document = {getElementById() {return null;}, querySelectorAll(selector) {
            if (selector===args.search_selector) return [node('input',{type:'search',value:args.marker})];
            if (selector===args.filter_selector) return [node('button',{'aria-selected':'true',innerText:args.filter})];
            return [table];
        }};
        console.log(JSON.stringify(eval(project)(null,args)));
        """
        bindings = replace(self.bindings, cells=cells)
        for mode, expected in (
            ("adjacent-avatar", "owned"), ("hidden", "none"), ("wrong-column", "none"),
            ("duplicate", "multiple"), ("ambiguous", "conflict"),
        ):
            with self.subTest(mode=mode):
                def browser(_tab, _tool, args):
                    result = subprocess.run(
                        ["node", "-e", fixture, json.dumps([args["expression"], args["arg"], mode])],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr[-1200:])
                    return browser_json(json.loads(result.stdout))

                self.assertEqual(observe_owned_search(browser, "tab", bindings, self.query).match, expected)

    def test_direct_bindings_must_match_exact_host_marker_and_distinct_columns(self):
        marker = OwnedRowCell(1, self.query.marker, "div.name")
        browser = Mock()
        for cells in (
            (marker, OwnedRowCell(1, self.query.identity[0]), OwnedRowCell(2, self.query.identity[1])),
            (marker, OwnedRowCell(3, "other"), OwnedRowCell(2, self.query.identity[1])),
        ):
            result = observe_owned_search(browser, "tab", replace(self.bindings, cells=cells), self.query)
            self.assertEqual(result.status, "read_failed")
        browser.assert_not_called()

    def test_filterless_query_requires_an_explicit_matching_no_filter_binding(self):
        query = replace(self.query, filter=None)
        scope = replace(self.bindings, filter_selector=None)
        browser = Mock(return_value=browser_json({"scope":True,"marker_count":1,"identity_matches":[True,True]}))
        self.assertEqual(observe_owned_search(browser, "tab", self.bindings, query).status, "read_failed")
        self.assertEqual(observe_owned_search(browser, "tab", scope, self.query).status, "read_failed")
        browser.assert_not_called()
        result = observe_owned_search(browser, "tab", scope, query)
        self.assertEqual((result.status,result.match), ("partial","owned"))


class SearchCompletionAdmissionTests(unittest.TestCase):
    query = OwnedSearchTests.query

    def sample(self, **changes):
        fields = {
            "scope_current": True, "query_matches": True, "after_exact_input": True,
            "busy": False, "error_visible": False, "data_rows": 0,
        }
        return SearchLifecycleSample(**(fields | changes))

    def admit(self, *samples):
        return admit_search_completion(self.query, "assigned-tab", tuple(samples), "timeline")

    def test_pre_fill_idle_can_lack_coverage_but_positive_post_fill_coverage_is_required(self):
        initial = self.sample(query_matches=False, after_exact_input=False, data_rows=7)
        busy = self.sample(busy=True)
        final_counter = self.sample(total=0)
        final_empty = self.sample(scoped_empty=True)
        for final in (final_counter, final_empty):
            self.assertEqual(self.admit(initial, busy, final),
                             SearchCompleted(self.query, "timeline", "assigned-tab"))
        self.assertIsNone(self.admit(initial, busy, self.sample()))

    def test_end_state_rejects_inconsistent_empty_and_incomplete_coverage(self):
        initial = self.sample(query_matches=False, after_exact_input=False, data_rows=7)
        busy = self.sample(busy=True)
        for final in (self.sample(total=5, data_rows=2), self.sample(total=2, scoped_empty=True),
                      self.sample(scoped_empty=True, data_rows=1), self.sample(total=True, scoped_empty=True)):
            self.assertIsNone(self.admit(initial, busy, final))

    def test_exact_input_and_post_dispatch_busy_pulse_are_never_inferred(self):
        initial = self.sample(query_matches=False, after_exact_input=False)
        final = self.sample(total=0)
        self.assertIsNone(self.admit(initial, final))
        self.assertIsNone(self.admit(initial, self.sample(busy=True, after_exact_input=False), final))
        self.assertIsNone(self.admit(initial, self.sample(busy=True, query_matches=False), final))
        self.assertIsNone(self.admit(self.sample(busy=True, query_matches=False, after_exact_input=False), final))

    def test_scope_changes_errors_and_latest_loading_invalidate_a_previous_cycle(self):
        initial = self.sample(query_matches=False, after_exact_input=False)
        busy = self.sample(busy=True)
        final = self.sample(total=0)
        for interrupted in (self.sample(scope_current=False), self.sample(error_visible=True),
                            self.sample(busy=True), self.sample(after_exact_input=False)):
            self.assertIsNone(self.admit(initial, busy, final, interrupted))
