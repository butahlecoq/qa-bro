import unittest
from unittest.mock import Mock

from qabro.browse_transport import BrowseTransport


class BrowseTransportTests(unittest.TestCase):
    def test_request_wait_is_capped_by_attempt_budget(self):
        budget = Mock()
        budget.remaining_seconds.return_value = 0.25
        transport = BrowseTransport(timeout=10, budget=budget)
        transport._selector = Mock()
        transport._selector.select.return_value = []
        transport._send = Mock()
        with self.assertRaises(TimeoutError):
            transport.request("tools/call", {})
        (wait,), _ = transport._selector.select.call_args
        self.assertGreater(wait, 0)
        self.assertLessEqual(wait, 0.25)
