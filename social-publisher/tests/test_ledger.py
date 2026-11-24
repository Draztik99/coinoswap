"""Offline tests of at-most-once reservations and state transitions."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ledger import LedgerError, PublicationLedger

DAY = "2026-11-23"
HASH = "a" * 64


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "posts.sqlite")
        self.ledger = PublicationLedger(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def reserve(self, platform="x", request_id="req-1"):
        return self.ledger.reserve(platform, DAY, "daily_rates", HASH, request_id)

    def test_x_exactly_one_slot_per_day(self):
        self.assertTrue(self.reserve())
        self.assertFalse(self.reserve(request_id="req-2"))
        self.assertEqual(self.ledger.get("x", DAY, "daily_rates")["state"], "RESERVED")

    def test_other_platform_is_separate(self):
        self.assertTrue(self.reserve("x"))
        self.assertTrue(self.reserve("facebook"))
        self.assertTrue(self.reserve("instagram"))
        self.assertFalse(self.reserve("facebook", "different"))

    def test_two_process_style_connections_cannot_double_reserve(self):
        self.assertTrue(self.reserve("x"))
        second = PublicationLedger(self.db)
        self.assertFalse(second.reserve("x", DAY, "daily_rates", HASH, "req-2"))

    def test_unknown_delivery_is_not_retried(self):
        self.assertTrue(self.reserve())
        self.ledger.transition("x", DAY, "daily_rates", from_state="RESERVED", to_state="SENDING")
        self.ledger.transition("x", DAY, "daily_rates", from_state="SENDING", to_state="UNKNOWN",
                               error="timeout after request")
        self.assertFalse(self.reserve(request_id="blind-retry"))
        with self.assertRaises(LedgerError):
            self.ledger.transition("x", DAY, "daily_rates",
                                   from_state="UNKNOWN", to_state="SENDING")
        self.assertEqual(self.ledger.get("x", DAY, "daily_rates")["state"], "UNKNOWN")

    def test_receipt_can_reconcile_unknown(self):
        self.reserve()
        self.ledger.transition("x", DAY, "daily_rates", from_state="RESERVED", to_state="SENDING")
        self.ledger.transition("x", DAY, "daily_rates", from_state="SENDING", to_state="UNKNOWN")
        self.ledger.transition("x", DAY, "daily_rates", from_state="UNKNOWN", to_state="PUBLISHED",
                               provider_post_id="123", public_url="https://x.com/coinoswap/status/123")
        row = self.ledger.get("x", DAY, "daily_rates")
        self.assertEqual(row["state"], "PUBLISHED")
        self.assertEqual(row["provider_post_id"], "123")

    def test_no_published_state_without_receipt(self):
        self.reserve()
        self.ledger.transition("x", DAY, "daily_rates", from_state="RESERVED", to_state="SENDING")
        with self.assertRaises(LedgerError):
            self.ledger.transition("x", DAY, "daily_rates", from_state="SENDING", to_state="PUBLISHED")

    def test_no_duplicate_after_pre_send_failure(self):
        self.reserve()
        self.ledger.transition("x", DAY, "daily_rates", from_state="RESERVED",
                               to_state="FAILED_PRE_SEND", error="no media")
        self.assertFalse(self.reserve(request_id="unapproved-retry"))

    def test_wrong_current_state_blocked(self):
        self.reserve()
        with self.assertRaisesRegex(LedgerError, "unexpected current state"):
            self.ledger.transition("x", DAY, "daily_rates",
                                   from_state="SENDING", to_state="UNKNOWN")

    def test_invalid_platform_rejected(self):
        with self.assertRaisesRegex(LedgerError, "unknown platform"):
            self.reserve("twitter")

    def test_invalid_digest_rejected(self):
        with self.assertRaisesRegex(LedgerError, "hash"):
            self.ledger.reserve("x", DAY, "daily_rates", "wrong", "request")


if __name__ == "__main__":
    unittest.main()
