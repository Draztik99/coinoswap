"""Exercise the at-most-once policy under simulated outages and concurrency."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ledger import PublicationLedger
from simulation import MockOutcome, simulate_publication

SHA = "c" * 64
DAY = "2026-11-23"


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = PublicationLedger(Path(self.tmp.name) / "ledger.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def test_mock_x_success_once_only(self):
        ok = MockOutcome("success", "111", "https://x.com/CoinoSwap/status/111")
        self.assertEqual(simulate_publication(self.ledger,"x",DAY,SHA,ok).state, "PUBLISHED")
        self.assertFalse(simulate_publication(self.ledger,"x",DAY,SHA,ok).reserved)
        self.assertEqual(self.ledger.get("x",DAY,"daily_rates")["provider_post_id"], "111")

    def test_15_simultaneous_attempts_reserve_one_slot(self):
        ok = MockOutcome("success", "111", "https://x.com/CoinoSwap/status/111")
        def attempt(_):
            return simulate_publication(self.ledger,"x",DAY,SHA,ok)
        with ThreadPoolExecutor(max_workers=15) as pool:
            outcomes = list(pool.map(attempt, range(15)))
        self.assertEqual(sum(x.reserved for x in outcomes), 1)
        self.assertEqual(sum(x.post_count for x in outcomes), 1)

    def test_7_days_reserve_7_separate_x_posts(self):
        for day in range(23, 30):
            result = simulate_publication(self.ledger,"x",f"2026-11-{day}",SHA,
                                          MockOutcome("success",str(day),f"https://x.com/test/status/{day}"))
            self.assertTrue(result.reserved)
        self.assertFalse(simulate_publication(
            self.ledger,"x","2026-11-23",SHA,
            MockOutcome("success","new","https://x.com/test/status/new")).reserved)

    def test_platforms_have_independent_ledgers(self):
        for platform in ("x", "facebook", "instagram"):
            out = simulate_publication(self.ledger, platform, DAY, SHA, MockOutcome("timeout_after_send"))
            self.assertEqual(out.state, "UNKNOWN")
            self.assertEqual(self.ledger.get(platform,DAY,"daily_rates")["state"], "UNKNOWN")

    def test_timeout_rate_limit_and_auth_do_not_repost(self):
        for name in ("timeout_after_send", "http_401", "http_429", "http_500", "receipt_missing"):
            with self.subTest(name=name):
                day = f"2026-12-{len(name):02}"
                first = simulate_publication(self.ledger, "x", day, SHA, MockOutcome(name))
                second = simulate_publication(self.ledger, "x", day, SHA,
                                            MockOutcome("success","222","https://x.com/test/status/222"))
                self.assertEqual(first.state, "UNKNOWN")
                self.assertFalse(second.reserved)
                self.assertEqual(second.post_count, 0)

    def test_pre_send_failure_never_claims_published(self):
        out = simulate_publication(self.ledger, "x", DAY, SHA, MockOutcome("pre_send_failure"))
        self.assertEqual(out.state, "FAILED_PRE_SEND")
        self.assertEqual(out.post_count, 0)

    def test_success_without_receipt_becomes_unknown(self):
        out = simulate_publication(self.ledger, "instagram", DAY, SHA, MockOutcome("success"))
        self.assertEqual(out.state, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
