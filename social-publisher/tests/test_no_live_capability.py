"""Static check that shadow code still cannot send social requests."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class NoLiveCapabilityTests(unittest.TestCase):
    def test_shadow_modules_do_not_execute_social_writes(self):
        # A guardrail against accidentally introducing a live transport.
        forbidden = (
            "requests.post(", "httpx.post(", "http.client.HTTPSConnection",
            "requests.Session().post(", "urllib3.PoolManager(", "aiohttp.ClientSession(",
        )
        for path in ROOT.glob("*.py"):
            data=path.read_text(encoding="utf-8")
            for marker in forbidden:
                with self.subTest(path=path.name, marker=marker):
                    self.assertNotIn(marker,data)
        # No raw urlopen outside the pinned GitHub asset reader.\n        # The optional Facebook health probe can only perform a fixed GET and\n        # never runs under the default offline CI test workflow.
        for path in ROOT.glob("*.py"):
            if path.name != "asset_reader.py":
                self.assertNotIn("urlopen(",path.read_text("utf-8"))


    def test_optional_health_check_has_no_post_or_schedule(self):
        source = (ROOT / "facebook_health.py").read_text(encoding="utf-8")
        self.assertIn('method="GET"', source)
        self.assertIn("GRAPH_ME_URL", source)
        self.assertIn("_RejectRedirects()", source)
        self.assertNotIn('method="POST"', source)
        self.assertNotIn("scheduler", source.lower().split("if __name__")[0][-300:])


if __name__=="__main__":
    unittest.main()
