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
