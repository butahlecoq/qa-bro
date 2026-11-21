import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Catalog, Scope, SkillRef


class CatalogTests(unittest.TestCase):
    def test_search_respects_scope_capabilities_and_pinned_revision(self):
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "catalog.sqlite"
        catalog = Catalog(path)
        scope = Scope("fixture", "combobox", "requirements", "editor")
        first = SkillRef("counterparty", "1", "Search counterparty dropdown")
        second = SkillRef("counterparty", "2", first.summary)
        catalog.pin("empty")
        catalog.seed_verified_hint(first, scope, "Type three characters.", capabilities=frozenset({"snapshot"}))
        catalog.pin("before")
        catalog.seed_verified_hint(second, scope, "Type four characters.")
        catalog = Catalog(path)
        catalog.pin("before")
        catalog.pin("after")
        tools = frozenset({"snapshot"})
        self.assertEqual(catalog.search("empty", "counterparty", scope, tools), [])
        self.assertEqual(catalog.search("before", "counterparty", scope, frozenset()), [])
        self.assertEqual(catalog.search("before", "counterparty", scope, tools), [first])
        self.assertEqual(catalog.search("after", "counterparty", scope, tools), [second])
        wrong_role = Scope("fixture", "combobox", "requirements", "viewer")
        self.assertEqual(catalog.search("after", "counterparty", wrong_role, tools), [])
        self.assertEqual(catalog.load_hint("before", first), "Type three characters.")
        self.assertIsNone(catalog.load_hint("before", second))

    def test_quarantine_rolls_back_only_compatible_nonquarantined_revisions(self):
        directory = self.enterContext(TemporaryDirectory())
        catalog = Catalog(Path(directory) / "catalog.sqlite")
        scope = Scope("fixture", "combobox", "requirements", "editor")
        other_scope = Scope("fixture", "combobox", "orders", "editor")
        previous = SkillRef("search", "1", "Search")
        unrelated = SkillRef("search", "2", "Search")
        active = SkillRef("search", "3", "Search")
        catalog.seed_verified_hint(previous, scope, "Old hint")
        catalog.seed_verified_hint(unrelated, other_scope, "Different screen")
        catalog.seed_verified_hint(active, scope, "New hint")
        catalog.pin("in-flight")
        catalog.quarantine(active, "Wrong result in the verified scope")
        catalog.quarantine(active, "Retry")
        catalog.pin("after-rollback")
        self.assertEqual(catalog.load_hint("in-flight", active), "New hint")
        self.assertEqual(catalog.search("after-rollback", "search", scope, frozenset()), [previous])

        catalog.quarantine(previous, "Also fails")
        catalog.pin("after-second-quarantine")
        self.assertEqual(catalog.search("after-second-quarantine", "search", scope, frozenset()), [])
        self.assertEqual(catalog.search("after-second-quarantine", "search", other_scope, frozenset()), [])

    def test_component_drift_invalidates_all_revisions_in_only_the_changed_scope(self):
        directory = self.enterContext(TemporaryDirectory())
        catalog = Catalog(Path(directory) / "catalog.sqlite")
        scope = Scope("fixture", "table", "requirements", "editor")
        independent_scope = Scope("fixture", "table", "orders", "editor")
        first = SkillRef("requirements-search", "1", "Search records")
        latest = SkillRef("requirements-search", "2", "Search records")
        independent = SkillRef("orders-search", "1", "Search records")
        catalog.seed_verified_hint(first, scope, "First workflow")
        catalog.seed_verified_hint(latest, scope, "Second workflow")
        catalog.seed_verified_hint(independent, independent_scope, "Independent workflow")
        catalog.pin("old")
        self.assertEqual(catalog.quarantine_scope(scope, "Component changed"), [first, latest])
        self.assertEqual(catalog.quarantine_scope(scope, "Retry"), [])
        catalog.pin("new")
        self.assertEqual(catalog.search("new", "search", scope, frozenset()), [])
        self.assertEqual(catalog.search("new", "search", independent_scope, frozenset()), [independent])
        self.assertEqual(catalog.search("old", "search", scope, frozenset()), [latest])
        from qabro.jobs import JobQueue

        queue = JobQueue(catalog.path)
        jobs = [queue.claim("revalidate", now_ns=1, lease_ns=10) for _ in range(2)]
        self.assertEqual([job.payload["skill"]["revision"] for job in jobs], ["1", "2"])
        self.assertEqual([job.payload["scope"]["context"] for job in jobs], ["requirements"] * 2)
        self.assertIsNone(queue.claim("revalidate", now_ns=1, lease_ns=10))
