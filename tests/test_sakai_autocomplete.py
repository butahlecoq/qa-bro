import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from qabro.sakai_autocomplete import KEYS, LEARNING_LABELS, LOCAL_URL, MODEL, component_tool, measure


class AutocompleteTests(unittest.TestCase):
    def test_pure_worker_cannot_discover_the_skill_action(self):
        pure = component_tool(assisted=False)["inputSchema"]["properties"]["action"]["enum"]
        assisted = component_tool(assisted=True)["inputSchema"]["properties"]["action"]["enum"]
        self.assertEqual(assisted, [*pure, "choose"])
        self.assertNotIn("choose", pure)

    def test_measurement_requires_a_validated_candidate_and_fresh_inputs(self):
        output = Path(self.enterContext(TemporaryDirectory()))
        acquisition = output / "acquisition.json"
        data = {
            "status": "declined", "url": LOCAL_URL, "model": MODEL, "schema": "schema",
            "knowledge": {"component": "PrimeVue AutoComplete", "keys": list(KEYS)},
            "learning_labels": LEARNING_LABELS,
        }

        def attempt(label):
            measure(output, "opencode", "browse", LOCAL_URL, "schema", acquisition, (label,))

        with patch("qabro.sakai_autocomplete.run_case") as browser:
            acquisition.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Acquisition does not match"):
                attempt("Nepal")
            data["status"] = "active"
            acquisition.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "separate from learning"):
                attempt(LEARNING_LABELS[0])
            browser.assert_not_called()
