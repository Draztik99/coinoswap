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
        # Read-only network access exists exclusively in the pinned GitHub asset reader.
        for path in ROOT.glob("*.py"):
            if path.name != "asset_reader.py":
                self.assertNotIn("urlopen(",path.read_text("utf-8"))


if __name__=="__main__":
    unittest.main()
