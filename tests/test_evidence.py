import unittest

from qabro.contract import Checkpoint, Observation
from qabro.evidence import CheckWindow, Evidence


class EvidenceTests(unittest.TestCase):
    def test_eventual_check_has_a_fixed_deadline(self):
        window = CheckWindow(Checkpoint("saved", "Record appears", wait_ns=10), 100)
        missing = Evidence(109, "snapshot-1", False)
        self.assertEqual(window.evaluate(missing, now_ns=109), Observation.PENDING)
        self.assertEqual(window.evaluate(missing, now_ns=110), Observation.MISMATCH)
        appeared_late = Evidence(111, "snapshot-2", True)
        self.assertEqual(window.evaluate(appeared_late, now_ns=111), Observation.UNVERIFIED)

    def test_match_at_deadline_is_accepted(self):
        window = CheckWindow(Checkpoint("saved", "Record appears", wait_ns=10), 100)
        self.assertEqual(window.evaluate(Evidence(110, "snapshot", True), now_ns=112), Observation.MATCH)

    def test_immediate_check_distinguishes_missing_evidence_from_mismatch(self):
        window = CheckWindow(Checkpoint("disabled", "Button is disabled"), 100)
        self.assertEqual(window.evaluate(None, now_ns=101), Observation.UNVERIFIED)
        self.assertEqual(window.evaluate(Evidence(101, "snapshot", False), now_ns=101), Observation.MISMATCH)
