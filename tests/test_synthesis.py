import unittest

from qabro.jobs import Job
from qabro.synthesis import synthesize_hint


class SynthesisTests(unittest.TestCase):
    def test_structured_response_becomes_a_candidate_with_model_cost(self):
        job = Job("job", "explore", {"operation": "Select category"}, "lease")

        def ask(prompt):
            self.assertIn("Select category", prompt)
            self.assertIn("options appeared", prompt)
            return '{"summary":"Category","hint":"Open the field","variants":["open"]}', 42

        result = synthesize_hint(job, (b"options appeared",), ask)
        self.assertEqual(result.hint, "Open the field")
        self.assertEqual(result.model_tokens, 42)
        self.assertIsNone(synthesize_hint(job, (), lambda _: ("null", 10)))
        with self.assertRaises(ValueError):
            synthesize_hint(job, (), lambda _: ('{"summary":"missing fields"}', 1))
