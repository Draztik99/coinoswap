"""Offline-only Facebook Page published-post reconciliation tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from facebook_reconciliation import (
    POST_FIELDS, PAGE_SIZE, published_posts_lookup_spec, scan_published_posts,
)
from contracts import ContractRejected

PAGE = "108130358772133"
DAY = "2026-11-24"


class FacebookReconciliationTests(unittest.TestCase):
    def test_lookup_contract_is_read_only(self):
        spec = published_posts_lookup_spec()
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.operation, "read_page_published_posts")
        self.assertEqual(spec.body, {"fields": POST_FIELDS, "limit": PAGE_SIZE})
        self.assertIn(PAGE + "/published_posts", spec.url)
        self.assertNotIn("access_token", str(spec))
        self.assertNotIn("Bearer", str(spec))

    def test_candidate_detected_in_sast_day(self):
        response = {"data": [{"id": PAGE + "_876",
                              "message": "BTC • ETH • XMR CoinoSwap Daily Rates",
                              "created_time": "2026-11-24T12:45:00+00:00"}]}
        r = scan_published_posts(response, date_sast=DAY)
        self.assertEqual(r.status, "POSSIBLE_DUPLICATE")
        self.assertEqual(r.possible_post_ids, (PAGE + "_876",))
        self.assertEqual(r.posts_created, 0)

    def test_cross_midnight_sast(self):
        response = {"data": [{"id": PAGE + "_876", "message": "BTC ETH XMR",
                              "created_time": "2026-11-23T22:30:00+00:00"}]}
        self.assertEqual(scan_published_posts(response, date_sast=DAY).status, "POSSIBLE_DUPLICATE")

    def test_no_match_does_not_authorize_posting(self):
        r = scan_published_posts({"data": []}, date_sast=DAY)
        self.assertEqual(r.status, "UNVERIFIED")
        self.assertEqual(r.posts_created, 0)

    def test_pagination_never_approves_clear(self):
        r = scan_published_posts({
            "data": [], "paging": {"next": "https://graph.facebook.com/next"}
        }, date_sast=DAY)
        self.assertEqual(r.status, "UNVERIFIED")
        self.assertFalse(r.all_pages_inspected)

    def test_missing_message_stays_unverified(self):
        r = scan_published_posts({"data": [
            {"id": PAGE + "_123", "created_time": "2026-11-24T12:00:00+00:00"}
        ]}, date_sast=DAY)
        self.assertFalse(r.all_pages_inspected)
        self.assertEqual(r.status, "UNVERIFIED")

    def test_invalid_response_stays_unverified(self):
        for response in ({}, {"data": "bad"}, {"error": {"message": "secret"}},
                         {"data": ["bad"]}, {"data": [], "paging": "bad"},
                         {"data": [{}]}):
            with self.subTest(response=response):
                r = scan_published_posts(response, date_sast=DAY)
                self.assertEqual(r.status, "UNVERIFIED")
                self.assertNotIn("secret", repr(r))

    def test_wrong_page_does_not_pass(self):
        r = scan_published_posts({"data": [{
            "id": "999_876", "message": "BTC ETH XMR",
            "created_time": "2026-11-24T12:45:00+00:00"
        }]}, date_sast=DAY)
        self.assertEqual(r.status, "UNVERIFIED")
        self.assertEqual(r.possible_post_ids, ())

    def test_invalid_date_rejected(self):
        for day in ("yesterday", "2026-13-10", "24-11-2026"):
            with self.assertRaises(ContractRejected):
                scan_published_posts({"data": []}, date_sast=day)

    def test_valid_other_day_is_not_candidate(self):
        r = scan_published_posts({"data": [{
            "id": PAGE + "_876", "message": "BTC ETH XMR",
            "created_time": "2026-11-23T10:00:00+00:00"
        }]}, date_sast=DAY)
        self.assertEqual(r.status, "UNVERIFIED")
        self.assertEqual(r.possible_post_ids, ())


if __name__ == "__main__":
    unittest.main()
