"""Mocked PostgreSQL ledger contract tests; no database connection."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import LedgerError
from receipts import verify_facebook_photo, VerifiedReceipt
from pg_ledger import (
    DurableLedger, RESERVE_SQL, TRANSITION_SQL, EXTERNAL_SQL,
)

DAY = "2026-11-24"
HASH = "a" * 64


class Cursor:
    def __init__(self, backend):
        self.backend = backend
        self.out = None
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def execute(self, sql, params):
        self.backend.calls.append((sql, params))
        if self.backend.raise_error:
            raise RuntimeError("simulated PostgreSQL unavailable")
        key = tuple(params[:3]) if sql == RESERVE_SQL or sql == EXTERNAL_SQL else tuple(params[4:7])
        if sql == RESERVE_SQL or sql == EXTERNAL_SQL:
            if key in self.backend.rows:
                self.out = None
            else:
                self.backend.rows[key] = (
                    "RESERVED" if sql == RESERVE_SQL else "PUBLISHED", "direct"
                    if sql == RESERVE_SQL else "metricool"
                )
                self.out = ("created",)
        else:
            state, origin = self.backend.rows.get(key, (None, None))
            prev = params[7]
            if state == prev and origin == "direct":
                self.backend.rows[key] = (params[0], "direct")
                self.out = (params[0],)
            else:
                self.out = None
    def fetchone(self):
        return self.out


class Connection:
    def __init__(self, backend):
        self.backend = backend
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def cursor(self):
        return Cursor(self.backend)


class FakeDatabase:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.raise_error = False
    def __call__(self):
        return Connection(self)


class PostgresLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.ledger = DurableLedger(self.db)

    def test_atomic_upsert_blocks_same_slot_across_workers(self):
        self.assertTrue(self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1"))
        second = DurableLedger(self.db)
        self.assertFalse(second.reserve("facebook", DAY, "daily_rates", HASH, "r2"))
        self.assertIn("ON CONFLICT", RESERVE_SQL)

    def test_unknown_cannot_blind_retry(self):
        self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")
        self.ledger.transition("facebook", DAY, "daily_rates",
                               from_state="RESERVED", to_state="SENDING")
        self.ledger.transition("facebook", DAY, "daily_rates",
                               from_state="SENDING", to_state="UNKNOWN")
        self.assertFalse(self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r2"))
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                                   from_state="UNKNOWN", to_state="SENDING")
        self.assertIn("state=%s", TRANSITION_SQL)

    def test_unverified_external_receipt_forbidden(self):
        with self.assertRaises(LedgerError):
            self.ledger.adopt_verified_metricool_receipt(
                "facebook", DAY, "daily_rates", HASH,
                provider_post_id="123", public_url="https://www.facebook.com/p/123")
        self.assertEqual(self.db.calls, [])

    def test_verified_metricool_blocks_direct_reservation(self):
        self.assertTrue(self.ledger.adopt_verified_metricool_receipt(
            "facebook", DAY, "daily_rates", HASH, independently_verified=True,
            provider_post_id="123", public_url="https://www.facebook.com/p/123"))
        self.assertFalse(self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "new"))
        self.assertIn("ON CONFLICT", EXTERNAL_SQL)

    def test_external_cannot_overwrite_reserved_direct(self):
        self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")
        self.assertFalse(self.ledger.adopt_verified_metricool_receipt(
            "facebook", DAY, "daily_rates", HASH, independently_verified=True,
            provider_post_id="123", public_url="https://www.facebook.com/p/123"))

    def test_published_requires_receipt(self):
        self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")
        self.ledger.transition("facebook", DAY, "daily_rates",
                               from_state="RESERVED", to_state="SENDING")
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                                   from_state="SENDING", to_state="PUBLISHED")


    def test_published_requires_matching_verified_facebook_readback(self):
        self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")
        self.ledger.transition("facebook", DAY, "daily_rates", from_state="RESERVED", to_state="SENDING")
        receipt = verify_facebook_photo("456", {
            "id": "456", "page_story_id": "108130358772133_222",
            "from": {"id": "108130358772133"},
            "link": "https://www.facebook.com/Coinoswap/posts/222",
        })
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                from_state="SENDING", to_state="PUBLISHED",
                provider_post_id="108130358772133_222", public_url=receipt.public_url)
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                from_state="SENDING", to_state="PUBLISHED",
                provider_post_id="999_222", public_url=receipt.public_url, verified_receipt=receipt)
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                from_state="SENDING", to_state="PUBLISHED",
                provider_post_id=receipt.provider_post_id, public_url="https://evil.example/x",
                verified_receipt=receipt)
        self.ledger.transition("facebook", DAY, "daily_rates",
            from_state="SENDING", to_state="PUBLISHED",
            provider_post_id=receipt.provider_post_id, public_url=receipt.public_url,
            verified_receipt=receipt)

    def test_raw_provider_error_or_token_cannot_enter_ledger(self):
        self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                from_state="RESERVED", to_state="FAILED_PRE_SEND", error="EAAG_SECRET_IN_ERROR")
        self.assertEqual(len(self.db.calls), 1)

    def test_wrong_state_is_blocked(self):
        self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DAY, "daily_rates",
                                   from_state="SENDING", to_state="UNKNOWN")

    def test_invalid_url_or_hash_blocked(self):
        with self.assertRaises(LedgerError):
            self.ledger.reserve("facebook", DAY, "daily_rates", "x", "r1")
        with self.assertRaises(LedgerError):
            self.ledger.adopt_verified_metricool_receipt(
                "facebook", DAY, "daily_rates", HASH, independently_verified=True,
                provider_post_id="123", public_url="https://example.com/post/123")

    def test_db_failure_propagates_no_fake_success(self):
        self.db.raise_error = True
        with self.assertRaises(RuntimeError):
            self.ledger.reserve("facebook", DAY, "daily_rates", HASH, "r1")

    def test_no_network_or_token_handling(self):
        from pathlib import Path
        code = (Path(__file__).resolve().parents[1] / "pg_ledger.py").read_text()
        self.assertNotIn("requests.post(", code)
        self.assertNotIn("urlopen(", code)
        self.assertNotIn("os.environ", code)
        self.assertNotIn("Authorization", code)


if __name__ == "__main__":
    unittest.main()
