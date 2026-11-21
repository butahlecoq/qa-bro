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

    def test_transfer_remains_a_hypothesis_until_validation(self):
        from qabro.compatibility import propose_transfer
        from qabro.jobs import JobQueue

        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "skills.sqlite"
        catalog, queue = Catalog(path), JobQueue(path)
        scope = Scope("fixture", "table", "requirements", "editor")
        target = Scope("another-platform", "table", "orders", "editor")
        ref = SkillRef("read-cell", "1", "Find cell")
        catalog.seed_verified_hint(ref, scope, "Read the cell")
        catalog.pin("run")
        job_id = propose_transfer(catalog, queue, "run", ref, target)
        self.assertEqual(propose_transfer(catalog, queue, "run", ref, target), job_id)
        self.assertEqual(catalog.confirmed_scope("run", ref), scope)
        catalog.pin("next-run")
        self.assertEqual(catalog.search("next-run", "cell", target, frozenset()), [])
        job = queue.claim("validate_transfer", now_ns=1, lease_ns=2)
        self.assertEqual(job.id, job_id)
        self.assertEqual(job.payload["target"]["platform"], target.platform)
