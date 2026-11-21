import unittest
from dataclasses import replace

from qabro.backend_evaluation import BackendPair, BackendRun, TraceEvent, TrialCase, evaluate_backend
from qabro.contract import Verdict


class BackendEvaluationTests(unittest.TestCase):
    def test_partial_effect_and_deadline_must_match_before_enabling_backend(self):
        pairs = []
        for case, verdict in zip(TrialCase, (Verdict.PASS, Verdict.FAIL, Verdict.INCONCLUSIVE)):
            plain = BackendRun("recipe", (TraceEvent("save", "checkpoint", verdict, "state", 20),),
                               verdict, 100, True)
            pairs.append(BackendPair(case, plain, replace(plain, elapsed_ns=80)))
        self.assertEqual(evaluate_backend(pairs, minimum_saved_ns=20)["decision"], "compiled")
        self.assertEqual(evaluate_backend(pairs[:-1], minimum_saved_ns=20)["decision"], "plain")
        self.assertEqual(evaluate_backend(pairs, minimum_saved_ns=21)["decision"], "plain")
        broken = replace(pairs[-1].compiled, events=(replace(pairs[-1].compiled.events[0], deadline_ns=30),))
        result = evaluate_backend([*pairs[:-1], replace(pairs[-1], compiled=broken)], minimum_saved_ns=20)
        self.assertEqual(result["mismatches"], [TrialCase.PARTIAL_EFFECT])
        self.assertEqual(result["decision"], "plain")
