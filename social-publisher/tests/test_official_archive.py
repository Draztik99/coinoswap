"""Official 2026-11-23 archived rate-image pair: immutable fixture only.

The fixed historical time makes this an offline test, NOT permission to
publish old crypto quotations today.
"""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"social-publisher"))
from asset_reader import AssetRejected, validate_asset_pair


class OfficialArchiveTests(unittest.TestCase):
    def test_real_official_pair_was_valid_at_original_slot(self):
        audit = (ROOT/"docs/daily-rates/2026-11-23.json").read_bytes()
        png = (ROOT/"docs/daily-rates/2026-11-23.png").read_bytes()
        approved = validate_asset_pair(audit,png,now=datetime.fromisoformat("2026-11-23T14:49:00+02:00"))
        self.assertEqual(approved.display_prices["BTC"], "$61,183.87")
        self.assertEqual(approved.date_sast, "2026-11-23")

    def test_archived_asset_cannot_be_reused_next_day(self):
        audit = (ROOT/"docs/daily-rates/2026-11-23.json").read_bytes()
        png = (ROOT/"docs/daily-rates/2026-11-23.png").read_bytes()
        with self.assertRaisesRegex(AssetRejected,"SAST publication date"):
            validate_asset_pair(audit,png,now=datetime.fromisoformat("2026-11-24T14:49:00+02:00"))


if __name__ == "__main__":
    unittest.main()
