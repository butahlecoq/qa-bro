import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from qabro.sakai_pi import bridge


class SakaiPiTests(unittest.TestCase):
    def test_bridge_accepts_only_the_session_token(self):
        calls = []
        with bridge(lambda request: calls.append(request) or {"status": "accepted"}) as env:
            address = env["QABRO_SAKAI_BRIDGE"]
            body = b'{"action":"inspect"}'
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(address, data=body), timeout=2)
            self.assertEqual(denied.exception.code, 403)
            denied.exception.close()
            request = Request(address, data=body, headers={
                "Authorization": "Bearer " + env["QABRO_SAKAI_TOKEN"],
            })
            with urlopen(request, timeout=2) as response:
                self.assertEqual(json.load(response), {"status": "accepted"})
        self.assertEqual(calls, [{"action": "inspect"}])

    def test_codex_refuses_api_key_login_before_model_invocation(self):
        from pathlib import Path
        from subprocess import CompletedProcess
        from unittest.mock import patch

        from qabro.sakai_pi import run_codex

        with patch("qabro.sakai_pi.subprocess.run", return_value=CompletedProcess(
            ["codex", "login", "status"], 0, "Logged in using an API key", "",
        )) as invoked:
            with self.assertRaisesRegex(RuntimeError, "signed in using ChatGPT"):
                run_codex("codex", "model", "prompt", Path("."), timeout=5,
                          env={"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "http://example.invalid"})
        self.assertEqual(invoked.call_count, 1)
        self.assertNotIn("OPENAI_API_KEY", invoked.call_args.kwargs["env"])
        self.assertNotIn("OPENAI_BASE_URL", invoked.call_args.kwargs["env"])

    def test_worker_counts_inspection_and_skill_reads_as_tool_calls(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from urllib.request import Request, urlopen

        from qabro.sakai_pi import worker_driver

        directory = Path(self.enterContext(TemporaryDirectory()))
        skill = directory / "SKILL.md"
        skill.write_text("Use the tested selector.")

        def launch(*_, env, **kwargs):
            for action in ("read_skill", "inspect", "click"):
                request = Request(env["QABRO_SAKAI_BRIDGE"], data=json.dumps({"action": action}).encode(),
                                  headers={"Authorization": "Bearer " + env["QABRO_SAKAI_TOKEN"]})
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
            return "done", 100, 4, "session"

        result = worker_driver("pi", "fixture", directory, skill, launch=launch)(lambda _: {})
        self.assertEqual(result[-2:], (True, 3))

    def test_trace_replay_dispatches_ordered_actions_only_once(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from qabro.sakai_pi import worker_driver

        directory = Path(self.enterContext(TemporaryDirectory()))
        calls = []
        actions = [{"tool": "click", "selector": "#new"}, {"tool": "click", "selector": "#save"}]

        def launch(*_, env, **kwargs):
            def replay():
                request = Request(env["QABRO_SAKAI_BRIDGE"], data=b'{"action":"replay"}',
                                  headers={"Authorization": "Bearer " + env["QABRO_SAKAI_TOKEN"]})
                with urlopen(request, timeout=2) as response:
                    return json.load(response)
            self.assertEqual(replay(), {"status": "creation_complete"})
            self.assertIn("error", replay())
            return "done", 100, 2, "session"

        def dispatch(request):
            calls.append(request)
            return {"status": "creation_complete" if request["selector"] == "#save" else "accepted"}

        result = worker_driver(
            "pi", "fixture", directory, None, launch=launch, replay_actions=actions,
        )(dispatch)
        self.assertEqual(result[-2:], (True, 2))
        self.assertEqual(calls, [{"action": "click", "selector": "#new"}, {"action": "click", "selector": "#save"}])

    def test_batch_fills_requires_executable_replay_at_cli_entry(self):
        import subprocess
        import sys

        result = subprocess.run([
            sys.executable, "-m", "qabro.sakai_pi", "unused", "--model", "fixture", "--batch-fills",
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--batch-fills requires --replay-creation", result.stderr)
