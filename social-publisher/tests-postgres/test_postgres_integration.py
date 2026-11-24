"""Real PostgreSQL CI integration tests, using a disposable test database ONLY.

This suite is kept separate from the regular offline tests. It only runs
when the explicit COINOSWAP_TEST_PG_DSN environment variable is present.
No Meta secrets, social API, scheduling, or Facebook POST is used.
"""
from __future__ import annotations

import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ledger import LedgerError
from receipts import verify_facebook_photo
from pg_ledger import DurableLedger

try:
    import psycopg
except ImportError:
    psycopg = None

DSN = os.environ.get("COINOSWAP_TEST_PG_DSN")
DATE = "2026-11-24"
HASH = "a" * 64


@unittest.skipUnless(DSN is not None and psycopg is not None,
                     "Disposable PostgreSQL test DSN and psycopg required")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = DSN
        # The CI runner provides a disposable PostgreSQL 16 service container.
        schema = (Path(__file__).resolve().parents[1] / "postgres_schema.sql").read_text()
        with psycopg.connect(cls.dsn, connect_timeout=5) as conn:
            for statement in schema.split(";"):
                if statement.strip():
                    conn.execute(statement)
        cls.factory = staticmethod(lambda: psycopg.connect(cls.dsn, connect_timeout=5))

    def setUp(self):
        with self.factory() as conn:
            conn.execute("TRUNCATE coinoswap_social_publications")
        self.ledger = DurableLedger(self.factory)

    def count(self):
        with self.factory() as conn:
            return conn.execute("SELECT COUNT(*) FROM coinoswap_social_publications").fetchone()[0]

    def test_sixteen_parallel_workers_reserve_once(self):
        def one(i):
            return self.ledger.reserve("facebook", DATE, "daily_rates", HASH, f"worker-{i}")
        with ThreadPoolExecutor(max_workers=16) as pool:
            result = list(pool.map(one, range(16)))
        self.assertEqual(sum(result), 1)
        self.assertEqual(self.count(), 1)

    def test_external_verified_post_blocks_direct_same_day(self):
        self.assertTrue(self.ledger.adopt_verified_metricool_receipt(
            "facebook", DATE, "daily_rates", HASH,
            provider_post_id="123", public_url="https://www.facebook.com/123/posts/123",
            independently_verified=True,
        ))
        self.assertFalse(self.ledger.reserve("facebook", DATE, "daily_rates", HASH, "direct-1"))
        self.assertEqual(self.count(), 1)

    def test_reserved_direct_post_blocks_external_overwrite(self):
        self.assertTrue(self.ledger.reserve("facebook", DATE, "daily_rates", HASH, "direct-1"))
        self.assertFalse(self.ledger.adopt_verified_metricool_receipt(
            "facebook", DATE, "daily_rates", HASH, provider_post_id="123",
            public_url="https://www.facebook.com/123/posts/123",
            independently_verified=True,
        ))
        with self.factory() as conn:
            status = conn.execute(
                "SELECT state, source FROM coinoswap_social_publications"
            ).fetchone()
        self.assertEqual(status, ("RESERVED", "direct"))

    def test_unknown_state_blocks_blind_retry(self):
        self.assertTrue(self.ledger.reserve("facebook", DATE, "daily_rates", HASH, "direct-1"))
        self.ledger.transition("facebook", DATE, "daily_rates",
                               from_state="RESERVED", to_state="SENDING")
        self.ledger.transition("facebook", DATE, "daily_rates",
                               from_state="SENDING", to_state="UNKNOWN")
        self.assertFalse(self.ledger.reserve("facebook", DATE, "daily_rates", HASH, "direct-2"))
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DATE, "daily_rates",
                                   from_state="UNKNOWN", to_state="SENDING")
        self.assertEqual(self.count(), 1)

    def test_published_requires_receipt(self):
        self.assertTrue(self.ledger.reserve("facebook", DATE, "daily_rates", HASH, "direct-1"))
        self.ledger.transition("facebook", DATE, "daily_rates",
                               from_state="RESERVED", to_state="SENDING")
        with self.assertRaises(LedgerError):
            self.ledger.transition("facebook", DATE, "daily_rates",
                                   from_state="SENDING", to_state="PUBLISHED")
        receipt = verify_facebook_photo("456", {
            "id": "456", "page_story_id": "108130358772133_456",
            "from": {"id": "108130358772133"},
            "link": "https://www.facebook.com/Coinoswap/posts/456",
        })
        self.ledger.transition(
            "facebook", DATE, "daily_rates", from_state="SENDING", to_state="PUBLISHED",
            provider_post_id=receipt.provider_post_id, public_url=receipt.public_url,
            verified_receipt=receipt)
        self.assertEqual(self.count(), 1)

    def test_invalid_receipt_never_written(self):
        with self.assertRaises(LedgerError):
            self.ledger.adopt_verified_metricool_receipt(
                "facebook", DATE, "daily_rates", HASH, provider_post_id="fake",
                public_url="https://evil.example/fake", independently_verified=True)
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main()
