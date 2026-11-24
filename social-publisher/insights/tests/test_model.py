"""Pure, offline analytics model tests: no Meta requests or fake results presented as real."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import (AnalyticsError, facebook_post_snapshot,
                   instagram_metricool_row, FIELDS)

NOW = datetime.fromisoformat("2026-11-24T20:00:00+02:00")
RECEIPT = {
    "platform":"facebook", "status":"PUBLISHED",
    "provider_post_id":"108130358772133_1137307232527711",
    "public_url":"https://www.facebook.com/photo.php?fbid=1137307215861046",
    "date_sast":"2026-11-24", "published_at_sast":"2026-11-24T19:19:05+02:00"
}
POST = {"id":RECEIPT["provider_post_id"],"from":{"id":"108130358772133"},
        "reactions":{"summary":{"total_count":4}},
        "comments":{"summary":{"total_count":0}},
        "shares":{"count":1}}

class NormalizerTests(unittest.TestCase):
    def test_facebook_measured_zero_distinct_from_missing(self):
        result=facebook_post_snapshot(POST,RECEIPT,collected_at=NOW)
        self.assertEqual(result["metrics"]["comments"],0)
        self.assertEqual(result["metrics"]["interactions"],5)
        self.assertIsNone(result["metrics"]["reach"])
        self.assertIsNone(result["metrics"]["views"])
        self.assertEqual(result["metric_status"],"partial")
        self.assertTrue(all(name in result["metrics"] for name in FIELDS))

    def test_partial_page_summary_cannot_infer_engagement(self):
        r=facebook_post_snapshot({**POST,"shares":{}},RECEIPT,collected_at=NOW)
        self.assertIsNone(r["metrics"]["shares"])
        self.assertIsNone(r["metrics"]["interactions"])

    def test_wrong_page_and_post_are_rejected(self):
        for p in ({**POST,"id":"999_123"},{**POST,"from":{"id":"999"}}):
            with self.assertRaises(AnalyticsError):
                facebook_post_snapshot(p,RECEIPT,collected_at=NOW)

    def test_graph_media_view_only_when_present(self):
        r=facebook_post_snapshot(POST,RECEIPT,collected_at=NOW,
            media_insights={"data":[{"name":"post_media_view","values":[{"value":9}]}]})
        self.assertEqual(r["metrics"]["views"],9)
        with self.assertRaises(AnalyticsError):
            facebook_post_snapshot(POST,RECEIPT,collected_at=NOW,
                media_insights={"data":[{"name":"post_media_view","values":[{"value":-1}]}]})

    def test_instagram_provider_values_preserve_zero_and_unavailable(self):
        row=["20261122121000","Daily Rates BTC ETH XMR","18123539791745350",
             "https://www.instagram.com/p/DgCxZXKDTe3/","0","0.0","0","0","3","0","0","4"]
        result=instagram_metricool_row(row,collected_at=NOW)
        self.assertEqual(result["metrics"]["reach"],3)
        self.assertEqual(result["metrics"]["views"],4)
        self.assertEqual(result["metrics"]["comments"],0)
        self.assertIsNone(result["metrics"]["link_clicks"])
        self.assertEqual(result["published_at_sast"],"2026-11-22T12:10:00+02:00")

    def test_malformed_metricool_row_rejected(self):
        with self.assertRaises(AnalyticsError):
            instagram_metricool_row(["bad"],collected_at=NOW)
        with self.assertRaises(AnalyticsError):
            instagram_metricool_row(["20261122121000","caption","bad",
                "https://www.instagram.com/p/a/","0","0.0","0","0","3","0","0","4"],
                collected_at=NOW)

    def test_secret_and_unsafe_url_rejected(self):
        with self.assertRaises(AnalyticsError):
            facebook_post_snapshot(POST,{**RECEIPT,"public_url":
                "https://www.facebook.com/photo.php?access_token=FAKE"},collected_at=NOW)

if __name__ == "__main__":
    unittest.main()
