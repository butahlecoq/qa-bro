import unittest
from datetime import UTC, datetime

from qabro.bindings import AttemptBindings, Generated, Literal, Option, Options, Select, UnresolvedBinding


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.bindings = AttemptBindings(
            {"name": Literal("Exact"), "code": Generated(4, "AB"), "item": Select(last=True)},
            seed=15,
            base_time=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def test_explicit_and_generated_values_are_stable(self):
        self.assertEqual(self.bindings.use("name"), "Exact")
        code = self.bindings.use("code")
        self.assertRegex(code, "^[AB]{4}$")
        self.assertEqual(self.bindings.use("code"), code)

    def test_last_option_requires_complete_observation(self):
        first, last = Option("1", "First"), Option("2", "Last")
        with self.assertRaises(UnresolvedBinding):
            self.bindings.use("item", options=Options((first,), complete=False))
        self.assertEqual(self.bindings.use("item", options=Options((first, last), True)), last)
        self.assertEqual(self.bindings.use("item", options=Options((last, first), True)), last)
        with self.assertRaises(UnresolvedBinding):
            self.bindings.use("item", options=Options((first,), True))

    def test_reopen_preserves_used_values_and_generation_sequence(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from qabro.journal import Journal

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        journal.start("a", "run", "worker")
        rules = {"first": Generated(8), "next": Generated(8), "item": Select(last=True)}
        time = datetime(2026, 1, 1, tzinfo=UTC)
        old = AttemptBindings(rules, seed=15, base_time=time, journal=journal, attempt="a")
        first = old.use("first")
        last = Option("2", "Last")
        old.use("item", options=Options((Option("1", "First"), last), True))
        control = AttemptBindings(rules, seed=15, base_time=time)
        self.assertEqual(control.use("first"), first)
        reopened = AttemptBindings(rules, seed=15, base_time=time, journal=Journal(path), attempt="a")
        self.assertEqual(reopened.use("first"), first)
        self.assertEqual(reopened.use("item"), last)
        self.assertEqual(reopened.use("next"), control.use("next"))
