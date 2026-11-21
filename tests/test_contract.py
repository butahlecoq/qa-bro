import unittest

from qabro.contract import Attempt, Checkpoint, Observation, Scenario, Step, Verdict, run_verdict


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.scenario = Scenario("source", (
            Step("open", "Open the form"),
            Step("save", "Click Save", (Checkpoint("saved", "Record appears"),)),
        ))

    def test_missing_expectation_does_not_acquire_an_assertion(self):
        attempt = Attempt(self.scenario, ("open", "save"), {"saved": Observation.MATCH})
        self.assertEqual(attempt.verdict, Verdict.PASS)

    def test_skipped_action_cannot_pass(self):
        attempt = Attempt(self.scenario, ("save",), {"saved": Observation.MATCH})
        self.assertEqual(attempt.verdict, Verdict.INCONCLUSIVE)

    def test_verified_failure_survives_successful_retry(self):
        failed = Attempt(self.scenario, ("open", "save"), {"saved": Observation.MISMATCH})
        passed = Attempt(self.scenario, ("open", "save"), {"saved": Observation.MATCH})
        self.assertEqual(run_verdict((failed, passed)), Verdict.FAIL)

    def test_attempts_cannot_combine_partial_evidence(self):
        first = Attempt(self.scenario, ("open",), {})
        second = Attempt(self.scenario, ("open", "save"), {})
        self.assertEqual(run_verdict((first, second)), Verdict.INCONCLUSIVE)
