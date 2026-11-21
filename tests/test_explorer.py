import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Scope
from qabro.explorer import Episode, queue_exploration
from qabro.jobs import JobQueue


class ExplorerTests(unittest.TestCase):
    def test_only_recurring_costly_operations_in_the_same_scope_enter_queue(self):
        directory = self.enterContext(TemporaryDirectory())
        queue = JobQueue(Path(directory) / "jobs.sqlite")
        scope = Scope("fixture", "calendar", "requirements", "editor")
        other = Scope("fixture", "calendar", "orders", "editor")
        episodes = [
            Episode(scope, "choose date", "a", "snapshot-a", 4),
            Episode(scope, "choose date", "a", "snapshot-a2", 3),
            Episode(scope, "choose date", "b", "snapshot-b", 1, discovered_behavior=True),
            Episode(other, "choose date", "c", "snapshot-c", 4),
            Episode(scope, "click save", "a", "snapshot-d", 4, routine_action=True),
            Episode(scope, "click save", "b", "snapshot-e", 4, routine_action=True),
        ]
        job_ids = queue_exploration(queue, episodes)
        self.assertEqual(len(job_ids), 1)
        self.assertEqual(queue_exploration(queue, list(reversed(episodes))), job_ids)
        job = queue.claim("explore", now_ns=1, lease_ns=10)
        self.assertEqual(job.payload["operation"], "choose date")
        self.assertEqual(job.payload["sources"], [
            {"attempt_id": "a", "evidence_id": "snapshot-a"},
            {"attempt_id": "b", "evidence_id": "snapshot-b"},
        ])
        self.assertIsNone(queue.claim("explore", now_ns=1, lease_ns=10))

    def test_scanner_restores_reported_episodes_from_disk(self):
        from qabro.explorer import record_episode, scan_experience
        from qabro.journal import Journal

        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "runs.sqlite"
        journal = Journal(path)
        queue = JobQueue(path)
        scope = Scope("fixture", "calendar", "requirements", "editor")
        for attempt in ("a", "b"):
            journal.start(attempt, "run", "worker")
            episode = Episode(scope, "choose date", attempt, f"artifact-{attempt}", 3)
            record_episode(journal, episode)
            record_episode(journal, episode)
        reopened = Journal(path)
        jobs = scan_experience(reopened, queue)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(scan_experience(reopened, queue), jobs)
        job = queue.claim("explore", now_ns=1, lease_ns=10)
        self.assertEqual([source["evidence_id"] for source in job.payload["sources"]], [
            "artifact-a", "artifact-b",
        ])

    def test_explorer_hands_draft_to_validation_without_publishing_it(self):
        from qabro.catalog import Catalog
        from qabro.explorer import HintDraft, explore_next

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        catalog, queue = Catalog(path), JobQueue(path)
        scope = Scope("fixture", "calendar", "requirements", "editor")
        queue_exploration(queue, [
            Episode(scope, "choose date", "a", "a-proof", 3),
            Episode(scope, "choose date", "b", "b-proof", 3),
        ])
        draft = HintDraft("Choose a date", "Use the date field.", ("date",), True, 20, 10)
        self.assertTrue(explore_next(queue, lambda job: draft, clock=lambda: 1))
        self.assertFalse(explore_next(queue, lambda job: self.fail("duplicate"), clock=lambda: 2))
        job = queue.claim("validate_hint", now_ns=2, lease_ns=10)
        self.assertEqual(job.payload["hint"], draft.hint)
        self.assertEqual(job.payload["sources"][0]["evidence_id"], "a-proof")
        catalog.pin("before-validation")
        self.assertEqual(catalog.search("before-validation", "date", scope, frozenset()), [])

    def test_existing_hint_only_deduplicates_the_matching_scope(self):
        from qabro.catalog import Catalog, SkillRef
        from qabro.explorer import HintDraft, explore_next

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        catalog, queue = Catalog(path), JobQueue(path)
        scope = Scope("fixture", "calendar", "requirements", "editor")
        other = Scope("fixture", "calendar", "orders", "editor")
        hint = "Use the date field."
        catalog.seed_verified_hint(SkillRef("date", "1", "Choose date"), scope, hint)
        for current in (scope, other):
            queue_exploration(queue, [
                Episode(current, "choose date", "a", "a-proof", 3),
                Episode(current, "choose date", "b", "b-proof", 3),
            ])
        draft = HintDraft("Choose a date", hint, ("date",), True, 20, 10)
        self.assertTrue(explore_next(queue, lambda _: draft, catalog=catalog, clock=lambda: 1))
        self.assertIsNone(queue.claim("validate_hint", now_ns=1, lease_ns=2))
        self.assertTrue(explore_next(queue, lambda _: draft, catalog=catalog, clock=lambda: 2))
        job = queue.claim("validate_hint", now_ns=2, lease_ns=2)
        self.assertEqual(job.payload["scope"], vars(other))

    def test_synthesis_receives_only_artifacts_linked_to_the_source_attempt(self):
        from qabro.artifacts import ArtifactStore
        from qabro.catalog import Catalog
        from qabro.explorer import HintDraft, explore_recorded
        from qabro.journal import Journal

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        catalog, journal, store = Catalog(path), Journal(path), ArtifactStore(path)
        scope = Scope("fixture", "select", "requirements", "editor")
        first = store.put(b"first snapshot", now=1)
        second = store.put(b"second snapshot", now=1)
        for attempt, evidence in (("a", first), ("b", second)):
            journal.start(attempt, "run", "worker")
            journal.append(attempt, "read:finish", "tool_finish", {"artifact_id": evidence})
        queue_exploration(catalog.jobs, [
            Episode(scope, "select", "a", second, 3),
            Episode(scope, "select", "b", first, 3),
        ])
        self.assertTrue(explore_recorded(catalog, lambda *_: self.fail("Unlinked artifacts"), clock=lambda: 1))
        self.assertIsNone(catalog.jobs.claim("validate_hint", now_ns=1, lease_ns=10))

        queue_exploration(catalog.jobs, [
            Episode(scope, "select", "a", first, 3),
            Episode(scope, "select", "b", second, 3),
        ])

        def synthesize(job, evidence):
            self.assertEqual(evidence, (b"first snapshot", b"second snapshot"))
            return HintDraft("Choose option", "Use the value", ("select",), False, 5, 0)

        self.assertTrue(explore_recorded(catalog, synthesize, clock=lambda: 2))
        self.assertIsNotNone(catalog.jobs.claim("validate_hint", now_ns=2, lease_ns=10))

    def test_runner_reports_costed_successful_steps_to_explorer(self):
        from time import monotonic_ns

        from qabro.browser import BrowserCalls
        from qabro.budget import Budget
        from qabro.contract import Checkpoint, Scenario, Step
        from qabro.evidence import Evidence
        from qabro.explorer import record_verified_steps, scan_experience
        from qabro.journal import Journal
        from qabro.runner import Action, run_scenario

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        queue, journal = JobQueue(path), Journal(path)
        scope = Scope("fixture", "select", "requirements", "editor")
        step = Step("choose", "Choose category", (Checkpoint("selected", "Category selected"),))
        for attempt in ("a", "b", "failed"):
            journal.start(attempt, "run", "worker")
            journal.claim_tab("shared", attempt, attempt)
            budget = Budget(browser_calls=1, model_calls=2, seconds=10)
            browser = BrowserCalls(journal, attempt, "shared", attempt,
                                   lambda *_: {"content": [{"type": "text", "text": "ok"}]},
                                   lambda value: value, budget=budget)

            def resolve(_):
                budget.consume("model")
                budget.consume("model")
                return Action("select", {})

            run_scenario(
                Scenario("Choose category", (step,)), browser, resolve,
                lambda *_: Evidence(monotonic_ns(), f"proof-{attempt}", attempt != "failed"),
                on_step_verified=record_verified_steps(journal, scope, attempt, lambda _: "category"),
            )

        self.assertEqual(len(scan_experience(journal, queue)), 1)
        job = queue.claim("explore", now_ns=1, lease_ns=10)
        self.assertEqual([source["attempt_id"] for source in job.payload["sources"]], ["a", "b"])
