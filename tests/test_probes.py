import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qabro.jobs import JobQueue
from qabro.journal import Journal
from qabro.probes import run_next_probe


class ProbeTests(unittest.TestCase):
    def test_probe_defers_under_load_and_while_worker_owns_resource(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, queue = Journal(path), JobQueue(path)
        journal.start("worker", "run", "worker")
        journal.claim_tab("shared", "worker-tab", "worker")
        journal.claim_resources("worker", ("record:test",))
        queue.enqueue("one", "probe", {"resources": ["record:test"]})
        calls = []

        def transport(tab, tool, arguments):
            calls.append((tab, tool))
            return {"content": [{"type": "text", "text": "done"}]}

        def execute(job, browser):
            result = browser.invoke("modify", "probe", "click", {})
            return {"outcome": result.outcome}

        args = {"context": "shared", "transport": transport,
                "redact": lambda value: value, "execute": execute,
                "allow_action": lambda job, tool, arguments: tool == "click"}
        self.assertFalse(run_next_probe(queue, journal, **args, foreground_busy=lambda: True, clock=lambda: 0))
        self.assertFalse(run_next_probe(queue, journal, **args, foreground_busy=lambda: False, clock=lambda: 0))
        self.assertEqual(calls, [])
        journal.release_resources("worker")
        self.assertTrue(run_next_probe(
            JobQueue(path), Journal(path), **args, foreground_busy=lambda: False,
            clock=lambda: 60_000_000_000,
        ))
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].startswith("probe-"))
        self.assertFalse(journal.claim_tab("shared", "worker-tab", "probe:one"))
        self.assertTrue(journal.claim_resources("worker", ("record:test",)))

    def test_expired_probe_recovers_without_executing_mutation_again(self):
        from qabro.recovery import Effect, reconcile

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, queue = Journal(path), JobQueue(path)
        queue.enqueue("one", "probe", {"resources": ["fixture:probe-record"]})
        calls = []

        def transport(tab, tool, arguments):
            calls.append(tool)
            if tool == "click":
                raise TimeoutError()
            return {"content": [{"type": "text", "text": "probe record present"}]}

        def execute(job, browser):
            browser.invoke("create", "probe", "click", {})
            return {"status": "completed"}

        def recover(job, browser):
            effect = reconcile(browser, "create", "fresh", "snapshot", {}, lambda _: Effect.COMPLETED)
            return {"status": "completed"} if effect is Effect.COMPLETED else None

        args = {"context": "shared", "transport": transport, "foreground_busy": lambda: False,
                "redact": lambda value: value, "execute": execute, "recover": recover,
                "allow_action": lambda job, tool, arguments: tool == "click"}
        with self.assertRaises(TimeoutError):
            run_next_probe(queue, journal, **args, clock=lambda: 0)
        self.assertTrue(run_next_probe(JobQueue(path), Journal(path), **args, clock=lambda: 60_000_000_000))
        self.assertEqual(calls, ["click", "snapshot"])
        self.assertIsNone(queue.claim("probe", now_ns=120_000_000_000, lease_ns=1))

    def test_expired_probe_cannot_start_a_browser_call(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, queue = Journal(path), JobQueue(path)
        queue.enqueue("old", "probe", {"resources": ["fixture:probe-record"]})
        now = 0

        def execute(job, browser):
            nonlocal now
            now = 60_000_000_000
            self.assertIsNotNone(queue.claim("probe", now_ns=now, lease_ns=10))
            browser.invoke("mutate", "probe", "click", {})
            self.fail("Expired worker must not dispatch")

        with self.assertRaisesRegex(PermissionError, "lease is no longer active"):
            run_next_probe(
                queue, journal, foreground_busy=lambda: False, context="shared",
                transport=lambda *_: self.fail("Stale call reached browser"),
                redact=lambda value: value, execute=execute, clock=lambda: now,
                allow_action=lambda *_: True,
            )

    def test_only_routine_confirmation_calls_the_confirm_action(self):
        from qabro.browser import BrowserCalls, Outcome, ToolResult
        from qabro.probes import Interruption, handle_interruption

        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal = Journal(path)
        journal.start("probe", "run", "explorer")
        browser = BrowserCalls(journal, "probe", "shared", "tab", lambda *_: {}, lambda value: value)
        confirmations = []

        def confirm():
            confirmations.append(True)
            return ToolResult(Outcome.RETURNED, {})

        cases = [
            (Interruption.CONFIRM, False, "confirmed"),
            (Interruption.DENIED, True, "expected_denial"),
            (Interruption.DENIED, False, "blocked"),
            (Interruption.EXPIRED_AUTH, False, "blocked"),
            (Interruption.HANDOFF, False, "blocked"),
        ]
        for index, (observed, expected, status) in enumerate(cases):
            result = handle_interruption(browser, step=str(index), evidence_id=f"snapshot-{index}",
                                         observed=observed, expected_denial=expected, confirm=confirm)
            self.assertEqual(result["status"], status)
        self.assertEqual(confirmations, [True])
        self.assertEqual(len(journal.events("probe")), len(cases))

    def test_probe_cannot_dispatch_to_an_unapproved_record(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "runs.sqlite"
        journal, queue = Journal(path), JobQueue(path)
        queue.enqueue("scope", "probe", {"resources": ["record:probe"]})

        def execute(job, browser):
            browser.invoke("outside", "probe", "click", {"selector": "#worker-record"}, read_only=True)
            self.fail("Unapproved mutation should stop the probe")

        self.assertTrue(run_next_probe(
            queue, journal, foreground_busy=lambda: False, context="shared",
            transport=lambda *_: self.fail("Unapproved command reached the browser"),
            redact=lambda value: value, execute=execute, clock=lambda: 1,
            allow_action=lambda job, tool, args: tool == "click" and args["selector"] == "#probe-record",
        ))
        events = journal.events("probe:scope")
        self.assertFalse(any(kind == "tool_start" for _, _, kind, _ in events))
        result, = [payload for _, _, kind, payload in events if kind == "probe_result"]
        self.assertEqual(result, {"status": "blocked", "reason": "action_outside_probe_plan"})
