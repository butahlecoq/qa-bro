import unittest

from qabro.explorer import NoCandidate
from qabro.jobs import Job
from qabro.synthesis import synthesize_hint


class SynthesisTests(unittest.TestCase):
    def test_structured_response_becomes_a_candidate_with_model_cost(self):
        job = Job("job", "explore", {"operation": "Select category"}, "lease")

        def ask(prompt):
            self.assertIn("Select category", prompt)
            self.assertIn("options appeared", prompt)
            return '{"summary":"Category","hint":"Open the field","variants":["open"],"support":"options appeared"}', 42

        result = synthesize_hint(job, (b"options appeared",), ask)
        self.assertEqual(result.hint, "Open the field")
        self.assertEqual(result.model_tokens, 42)
        self.assertEqual(synthesize_hint(job, (), lambda _: ("null", 10)), NoCandidate(10))
        with self.assertRaises(ValueError):
            synthesize_hint(job, (), lambda _: ('{"summary":"missing fields"}', 1))

    def test_omits_known_run_values_and_snapshot_refs_from_synthesis(self):
        job = Job("job", "explore", {"operation": "Select category"}, "lease")

        def ask(prompt):
            self.assertNotIn("Private fixture input", prompt)
            self.assertNotIn("ref=e42", prompt)
            self.assertIn("Category", prompt)
            return '{"summary":"Category","hint":"Click @e42","variants":["open"],"support":"Category"}', 13

        result = synthesize_hint(
            job, (b'Category [ref=e42] "Private fixture input"',), ask,
            run_values=("Private fixture input",),
        )
        self.assertEqual(result, NoCandidate(13))

    def test_declines_candidate_with_invented_support(self):
        job = Job("job", "explore", {"operation": "Select category"}, "lease")
        result = synthesize_hint(
            job, (b"options appeared",),
            lambda _: (
                '{"summary":"Category","hint":"Wait for search",'
                '"variants":["open"],"support":"search started"}',
                14,
            ),
        )
        self.assertEqual(result, NoCandidate(14))
