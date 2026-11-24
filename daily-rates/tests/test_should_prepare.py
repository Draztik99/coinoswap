"""Offline tests for Daily Rates GitHub gate, with no social access."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from should_prepare import PreparationBlocked, decide_preparation
from posting_slots import slot_for_date, expected_prepare_time

SAST = ZoneInfo("Africa/Johannesburg")
DAY = "2026-11-24"


def moment(hour, minute, sec=0):
    return datetime(2026, 11, 24, hour, minute, sec, tzinfo=SAST)


class PreparationGateTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name)

    def evaluate(self, hour, minute, *, emergency=False):
        return decide_preparation(
            moment(hour, minute), emergency=emergency, assets_dir=self.path
        )

    def write_pair(self):
        binary = b"TEST_PNG_BYTES_NOT_PUBLICATION_MEDIA"
        (self.path / (DAY + ".png")).write_bytes(binary)
        (self.path / (DAY + ".json")).write_text(json.dumps({
            "status": "VALIDATED", "date_sast": DAY,
            "image": {"filename": DAY + ".png", "sha256": hashlib.sha256(binary).hexdigest()}
        }), encoding="utf-8")

    def test_expected_slot_remains_frozen(self):
        self.assertEqual(slot_for_date(moment(14, 26).date()), (14, 30))
        self.assertEqual(expected_prepare_time(moment(14, 26).date()), (14, 26))

    def test_candidate_26_27_28_minute_windows(self):
        for minute in (26, 27, 28):
            with self.subTest(minute=minute):
                selected, reason = self.evaluate(14, minute)
                self.assertTrue(selected)
                self.assertIn("not yet", reason)

    def test_too_early_and_late_fail_closed(self):
        for hour, minute in ((14, 25), (14, 29), (14, 30), (2, 5), (15, 1)):
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(self.evaluate(hour, minute)[0], False)

    def test_emergency_still_requires_today_not_prior_day(self):
        selected, reason = self.evaluate(16, 20, emergency=True)
        self.assertTrue(selected)
        self.assertIn("fresh asset", reason)

    def test_valid_existing_pair_is_noop_even_with_emergency(self):
        self.write_pair()
        for emergency in (False, True):
            result = self.evaluate(14, 26, emergency=emergency)
            self.assertEqual(result[0], False)
            self.assertIn("no duplicate", result[1])

    def test_partial_pair_always_blocks(self):
        (self.path / (DAY + ".png")).write_bytes(b"partial")
        with self.assertRaisesRegex(PreparationBlocked, "incomplete"):
            self.evaluate(14, 26)

    def test_malformed_existing_pair_blocks(self):
        self.write_pair()
        (self.path / (DAY + ".json")).write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(PreparationBlocked, "unreadable"):
            self.evaluate(14, 26)

    def test_mismatched_hash_blocks(self):
        self.write_pair()
        (self.path / (DAY + ".png")).write_bytes(b"changed image")
        with self.assertRaisesRegex(PreparationBlocked, "checksum mismatch"):
            self.evaluate(14, 26)

    def test_wrong_day_and_unvalidated_pair_blocks(self):
        self.write_pair()
        p = self.path / (DAY + ".json")
        for update in ({"date_sast": "2026-11-23"}, {"status": "NOT_VALIDATED"}):
            with self.subTest(update=update):
                obj = json.loads(p.read_text(encoding="utf-8"))
                original = dict(obj)
                obj.update(update)
                p.write_text(json.dumps(obj), encoding="utf-8")
                with self.assertRaisesRegex(PreparationBlocked, "does not match"):
                    self.evaluate(14, 26)
                p.write_text(json.dumps(original), encoding="utf-8")

    def test_naive_timestamp_blocks(self):
        with self.assertRaisesRegex(PreparationBlocked, "clock"):
            decide_preparation(datetime(2026, 11, 24, 14, 26), assets_dir=self.path)


if __name__ == "__main__":
    unittest.main()
