import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Catalog, Scope, SkillRef
from qabro.compatibility import verified_capabilities


class CompatibilityTests(unittest.TestCase):
    def test_changed_tool_requires_smoke_check_at_skill_lookup(self):
        def schema(*tools):
            return {"tools": [
                {"name": name, "inputSchema": {"required": fields}}
                for name, fields in tools
            ]}

        previous = schema(("click", ["selector"]), ("fill", ["value"]), ("snapshot", []))
        current = schema(("click", ["ref"]), ("snapshot", []), ("select", ["values"]))
        required = frozenset({"click", "fill", "snapshot"})
        checked = []

        def smoke(name):
            checked.append(name)
            return False

        actual = verified_capabilities(previous, current, required, smoke)
        self.assertEqual(checked, ["click"])
        self.assertEqual(actual, frozenset({"snapshot"}))
        self.assertEqual(
            verified_capabilities(previous, current, required, lambda _: True),
            frozenset({"click", "snapshot"}),
        )

        directory = self.enterContext(TemporaryDirectory())
        catalog = Catalog(Path(directory) / "skills.sqlite")
        scope = Scope("fixture", "table", "requirements", "editor")
        click = SkillRef("click-cell", "1", "Find cell by clicking")
        read = SkillRef("read-cell", "1", "Find cell by reading")
        catalog.seed_verified_hint(click, scope, "Click the cell", capabilities=frozenset({"click"}))
        catalog.seed_verified_hint(read, scope, "Read the cell", capabilities=frozenset({"snapshot"}))
        catalog.pin("run")
        self.assertEqual(catalog.search("run", "cell", scope, actual), [read])
