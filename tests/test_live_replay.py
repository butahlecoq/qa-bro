import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.baseline import run_fixture
from qabro.browse_transport import BrowseTransport
from qabro.contract import Verdict
from qabro.journal import Journal


@unittest.skipUnless(os.environ.get("QABRO_FIXTURE_URL"), "Requires the live browser fixture")
class LiveReplayTests(unittest.TestCase):
    def test_plain_and_recipe_preserve_order_and_detect_wrong_category(self):
        executable = os.environ.get("QABRO_BROWSE", "browse")
        base_url = os.environ["QABRO_FIXTURE_URL"]
        parsed = urlsplit(base_url)
        database = Path(self.enterContext(TemporaryDirectory())) / "replay.sqlite"

        for suffix, expected in (("", Verdict.PASS), ("?wrong-category", Verdict.FAIL)):
            with self.subTest(verdict=expected):
                traces = []
                for replay in (False, True):
                    tab = f"replay-{uuid4().hex[:12]}"
                    with BrowseTransport(executable) as live:
                        live.prepare_tab(tab, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
                        try:
                            result = run_fixture(
                                executable, database, tab=tab, url=base_url + suffix, replay=replay,
                            )
                        finally:
                            live(tab, "tabs", {"action": "close"})
                    self.assertEqual(result["recipes"], int(replay))
                    self.assertIs(result["verdict"], expected)
                    check, = result["checkpoints"]
                    self.assertTrue(check["artifact_id"])
                    trace = [
                        (kind, event.get("step"), event.get("tool"), event.get("outcome"))
                        for _, _, kind, event in Journal(database).events(result["attempt"])
                        if kind in {"tool_start", "checkpoint"}
                    ]
                    traces.append(trace)
                self.assertEqual(traces[0], traces[1])
