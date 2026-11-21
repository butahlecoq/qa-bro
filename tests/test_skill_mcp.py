import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.catalog import Catalog, Scope, SkillRef


class SkillMcpTests(unittest.TestCase):
    def test_bad_input_does_not_interrupt_scoped_hint_lookup(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "catalog.sqlite"
        catalog = Catalog(path)
        catalog.seed_verified_hint(SkillRef("date", "1", "Choose date"),
                                   Scope("fixture", "form", "requirements", "editor"), "Use the date field.")
        calls = [
            ("read_hint", {"id": "date", "revision": "1"}),
            ("find_skills", {"query": 3}),
            ("find_skills", {"query": "date"}),
            ("read_hint", {"id": "date", "revision": "1"}),
        ]
        requests = ["{"] + [
            json.dumps({"jsonrpc": "2.0", "id": index, "method": "tools/call",
                        "params": {"name": tool, "arguments": args}})
            for index, (tool, args) in enumerate(calls)
        ]
        process = subprocess.run(
            [sys.executable, "-m", "qabro.skill_mcp", str(path), "run", "fixture", "form",
             "requirements", "editor"], input="\n".join(requests), text=True,
            capture_output=True, check=True, timeout=5,
        )
        invalid, early, wrong_type, lookup, hint = map(json.loads, process.stdout.splitlines())
        self.assertEqual(invalid["error"]["code"], -32700)
        self.assertTrue(early["result"]["isError"])
        self.assertTrue(wrong_type["result"]["isError"])
        self.assertIn("Choose date", lookup["result"]["content"][0]["text"])
        self.assertEqual(hint["result"]["content"][0]["text"], "Use the date field.")
