import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.baseline import run_fixture
from qabro.baseline_evidence import baseline_evidence
from qabro.browse_transport import BrowseTransport
from qabro.catalog import Catalog, SkillRef
from qabro.contract import Verdict
from qabro.journal import Journal
from qabro.validation import DefectTrial, _defect_evidence


@unittest.skipUnless(os.environ.get("QABRO_FIXTURE_URL"), "Requires the live browser fixture")
class LiveReplayTests(unittest.TestCase):
    def test_plain_and_recipe_preserve_order_and_detect_wrong_category(self):
        executable = os.environ.get("QABRO_BROWSE", "browse")
        base_url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(base_url)
        database = Path(self.enterContext(TemporaryDirectory())) / "replay.sqlite"

        for suffix, expected in (("", Verdict.PASS), ("?wrong-category", Verdict.FAIL)):
            with self.subTest(verdict=expected):
                traces = []
                results = []
                for replay in (False, True):
                    tab = f"replay-{uuid4().hex[:12]}"
                    with BrowseTransport(executable) as live:
                        live.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
                        try:
                            result = run_fixture(
                                executable, database, tab=tab, url=base_url + suffix, replay=replay,
                            )
                        finally:
                            live(tab, "tabs", {"action": "close"})
                    self.assertEqual(result["recipes"], int(replay))
                    self.assertIs(result["verdict"], expected)
                    if not replay:
                        proof = baseline_evidence(database, result["attempt"])
                        self.assertEqual(proof["browser_calls"], result["browser_calls"])
                        self.assertEqual(proof["verdict"], expected)
                    check, = result["checkpoints"]
                    self.assertTrue(check["artifact_id"])
                    trace = [
                        (kind, event.get("step"), event.get("tool"), event.get("outcome"))
                        for _, _, kind, event in Journal(database).events(result["attempt"])
                        if kind in {"tool_start", "checkpoint"}
                    ]
                    traces.append(trace)
                    results.append(result)
                self.assertEqual(traces[0], traces[1])
                if expected is Verdict.FAIL:
                    plain, replay = (result["attempt"] for result in results)
                    ref = SkillRef(f"fixture-fill:{replay}", "1", "Name date")
                    recipe = Catalog(database).load_recipe(replay, ref)
                    self.assertIsNotNone(recipe)
                    references = _defect_evidence(Journal(database), DefectTrial(plain, replay), recipe)
                    self.assertEqual(references, {
                        result["checkpoints"][0]["artifact_id"] for result in results
                    })

    def test_recipe_checks_fresh_browser_snapshot_before_acting(self):
        from datetime import UTC, datetime
        from time import monotonic_ns

        from qabro.artifacts import ArtifactStore
        from qabro.bindings import AttemptBindings
        from qabro.browser import BrowserCalls, Outcome
        from qabro.contract import Scenario, Step
        from qabro.recipe_checks import ProbeValue, RecipeCheck
        from qabro.runner import Action, Recipe, RecipeStep, run_scenario

        executable = os.environ.get("QABRO_BROWSE", "browse")
        url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(url)
        tab = f"guard-{uuid4().hex[:12]}"
        database = Path(self.enterContext(TemporaryDirectory())) / "guard.sqlite"
        journal, artifacts = Journal(database), ArtifactStore(database)
        journal.start(tab, tab, "worker")
        self.assertTrue(journal.claim_tab("fixture", tab, tab))
        opening, fill = Step("open", "Open form"), Step("fill", "Fill name")
        scenario = Scenario("Open the form and fill the name.", (opening, fill))
        recipe = Recipe("fill", "1", (RecipeStep(
            fill, "fill", (("selector", "input[name=name]"), ("value", "Guard sample")),
            guard=RecipeCheck("name-field", "visible", True),
        ),))

        with BrowseTransport(executable) as live:
            live.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
            try:
                browser = BrowserCalls(journal, tab, "fixture", tab, live, lambda value: value, artifacts=artifacts)

                def resolve(step):
                    self.assertEqual(step, opening)
                    return Action("navigate", {"url": url})

                def observe(step, probe):
                    self.assertEqual((step, probe), (fill, "name-field"))
                    result = browser.invoke("name-field", step.id, "snapshot", {}, read_only=True)
                    self.assertIs(result.outcome, Outcome.RETURNED)
                    return ProbeValue(monotonic_ns(), result.artifact_id, 'textbox "Name"' in str(result.raw))

                result = run_scenario(
                    scenario, browser, resolve, lambda *_: None,
                    choose=lambda step: recipe if step == fill else None, applicable=lambda _: True,
                    bindings=AttemptBindings({}, seed=1, base_time=datetime.now(UTC)), observe_recipe=observe,
                )
                self.assertIs(result.verdict, Verdict.PASS)
                field = live(tab, "eval", {
                    "selector": "input[name=name]", "expression": "element => element.value",
                })
                self.assertIn("Guard sample", str(field))
            finally:
                live(tab, "tabs", {"action": "close"})

        events = journal.events(tab)
        guard_sequence, _, _, guard = next(event for event in events if event[2] == "recipe_guard")
        dispatch_sequence = next(seq for seq, _, kind, data in events
                                 if kind == "tool_start" and data["tool"] == "fill")
        self.assertLess(guard_sequence, dispatch_sequence)
        self.assertTrue(guard["passed"])
        self.assertIsNotNone(artifacts.get(guard["artifact_id"]))
