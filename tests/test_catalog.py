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

    def test_changed_component_fingerprint_survives_restart_and_schedules_revalidation(self):
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "catalog.sqlite"
        catalog = Catalog(path)
        scope = Scope("fixture", "combobox", "requirements", "editor")
        ref = SkillRef("category", "1", "Select category")
        self.assertEqual(catalog.observe_component(scope, "before"), [])
        catalog.seed_verified_hint(ref, scope, "Choose the category")
        catalog = Catalog(path)
        self.assertEqual(catalog.observe_component(scope, "before"), [])
        self.assertEqual(catalog.observe_component(scope, "after"), [ref])
        self.assertEqual(catalog.observe_component(scope, "after"), [])
        catalog.pin("later")
        self.assertEqual(catalog.search("later", "category", scope, frozenset()), [])
        self.assertEqual(catalog.jobs.claim("revalidate", now_ns=1, lease_ns=10).payload["skill"]["id"], ref.id)

    def test_recipe_round_trips_with_the_pinned_skill_revision(self):
        from qabro.contract import Checkpoint, Step
        from qabro.runner import Parameter, Recipe, RecipeStep

        path = Path(self.enterContext(TemporaryDirectory())) / "catalog.sqlite"
        catalog = Catalog(path)
        scope = Scope("fixture", "form", "requirements", "editor")
        ref = SkillRef("fill", "1", "Fill field")
        step = Step("fill", "Fill name", (Checkpoint("filled", "Name matches", wait_ns=10),))
        recipe = Recipe(ref.id, ref.revision, (
            RecipeStep(step, "fill", (("selector", "input[name=name]"), ("value", Parameter("name")))),
        ))
        catalog.pin("before")
        with self.assertRaisesRegex(ValueError, "declared capabilities"):
            catalog.seed_verified_hint(ref, scope, "Fill the named field", recipe=recipe)
        catalog.seed_verified_hint(ref, scope, "Fill the named field", recipe=recipe,
                                   capabilities=frozenset({"fill"}))
        catalog.pin("after")
        reopened = Catalog(path)
        self.assertIsNone(reopened.load_recipe("before", ref))
        self.assertEqual(reopened.load_recipe("after", ref), recipe)

    def test_nested_recipe_pins_older_child_and_inherits_capability_requirement(self):
        from qabro.contract import Step
        from qabro.runner import Recipe, RecipeCall, RecipeStep

        catalog = Catalog(Path(self.enterContext(TemporaryDirectory())) / "catalog.sqlite")
        scope = Scope("fixture", "form", "requirements", "editor")
        child = SkillRef("child", "1", "Child")
        newer = SkillRef("child", "2", "Child")
        parent = SkillRef("parent", "1", "Parent")
        capabilities = frozenset({"fill"})
        step = RecipeStep(Step("fill", "Fill"), "fill", ())
        catalog.seed_verified_hint(child, scope, "Child", capabilities=capabilities,
                                   recipe=Recipe(child.id, child.revision, (step,)))
        parent_recipe = Recipe(parent.id, parent.revision, (RecipeCall(child.id, child.revision),))
        with self.assertRaisesRegex(ValueError, "necessary capabilities"):
            catalog.seed_verified_hint(parent, scope, "Parent", recipe=parent_recipe)
        catalog.seed_verified_hint(parent, scope, "Parent", capabilities=capabilities, recipe=parent_recipe)
        catalog.seed_verified_hint(newer, scope, "New child")
        catalog.pin("before-quarantine")
        self.assertIsNotNone(catalog.load_recipe("before-quarantine", child))
        catalog.quarantine(child, "Invalid child")
        catalog.pin("after-quarantine")
        self.assertIsNone(catalog.load_recipe("after-quarantine", parent))
        self.assertIsNotNone(catalog.load_recipe("before-quarantine", parent))

    def test_recipe_deduplication_preserves_steps_and_package_type(self):
        from dataclasses import replace

        from qabro.contract import Step
        from qabro.runner import Parameter, Recipe, RecipeStep

        catalog = Catalog(Path(self.enterContext(TemporaryDirectory())) / "catalog.sqlite")
        scope = Scope("fixture", "field", "requirements", "editor")
        hint = "Fill the named field."
        tools = frozenset({"fill"})
        ref = SkillRef("published", "2", "Fill field")
        step = RecipeStep(Step("fill", "Fill field"), "fill", (
            ("selector", "#name"), ("value", Parameter("name")),
        ))
        recipe = Recipe(ref.id, ref.revision, (step,))
        catalog.seed_verified_hint(ref, scope, hint, capabilities=tools, recipe=recipe)

        draft = replace(recipe, id="draft", revision="1")
        self.assertTrue(catalog.has_active_hint(scope, hint, tools, draft))
        self.assertFalse(catalog.has_active_hint(scope, hint, tools))
        changed = replace(draft, steps=(replace(step, guard="field-visible"),))
        self.assertFalse(catalog.has_active_hint(scope, hint, tools, changed))
