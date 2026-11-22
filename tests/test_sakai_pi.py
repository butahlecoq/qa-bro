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
