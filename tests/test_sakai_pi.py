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
