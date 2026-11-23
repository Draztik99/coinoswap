"""Offline funnel integrity, missing metrics and exact attribution."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import AnalyticsRejected, tracked_url, normalize_metrics, confirmed_swap_funnel


class AnalyticsTests(unittest.TestCase):
    def test_utm_url_for_x(self):
        url = tracked_url("x","2026-11-23")
        self.assertIn("utm_source=x",url)
        self.assertIn("utm_medium=organic_social",url)
        self.assertIn("utm_campaign=daily_rates",url)

    def test_instagram_metrics_do_not_invent_clicks(self):
        out = normalize_metrics("instagram", {"metric_source":"meta_api", "views":100,"likes":3})
        self.assertIsNone(out["link_clicks"])
        self.assertIsNone(out["impressions"])
        self.assertIsNone(out["engagement_rate"])

    def test_missing_metric_is_not_zero(self):
        out=normalize_metrics("x", {"metric_source":"x_api","impressions":0})
        self.assertEqual(out["impressions"],0)
        self.assertIsNone(out["views"])
        self.assertIsNone(out["likes"])

    def test_source_required(self):
        with self.assertRaises(AnalyticsRejected):
            normalize_metrics("x",{"impressions":500})

    def test_engagement_rate_only_when_all_counts_known(self):
        out = normalize_metrics("x",{"metric_source":"api","impressions":100,
            "likes":5,"comments":2,"shares":1,"reposts":2})
        self.assertEqual(out["engagement_rate"],0.1)

    def test_negative_counts_rejected(self):
        with self.assertRaises(AnalyticsRejected):
            normalize_metrics("x",{"metric_source":"api","views":-1})

    def test_instagram_per_post_link_clicks_not_assumed(self):
        with self.assertRaises(AnalyticsRejected):
            normalize_metrics("instagram",{"metric_source":"api","link_clicks":1})

    def test_verified_completions_only_and_exact_matching(self):
        sessions = [
            {"session_id":"s1","utm_source":"x"},
            {"session_id":"s1","utm_source":"x"}, # repeat page view, not a new session
            {"session_id":"s2","utm_source":"facebook"},
            {"session_id":"s3","utm_source":None},
        ]
        swaps = [
            {"swap_id":"one","session_id":"s1","status":"completed","verified":True,"volume_usd":"100.25"},
            {"swap_id":"one","session_id":"s1","status":"completed","verified":True,"volume_usd":"100.25"},
            {"swap_id":"two","session_id":"s2","status":"pending","verified":True,"volume_usd":"700"},
            {"swap_id":"three","session_id":"unknown","status":"completed","verified":True,"volume_usd":"50.00"},
            {"swap_id":"four","session_id":"s2","status":"completed","verified":False,"volume_usd":"1000"},
        ]
        result = confirmed_swap_funnel(sessions,swaps)
        self.assertEqual(result["tracked_sessions"],3)
        self.assertEqual(result["verified_completed_swaps"],2)
        self.assertEqual(result["attributed_completed_swaps"],1)
        self.assertEqual(result["unattributed_completed_swaps"],1)
        self.assertEqual(result["completed_volume_usd"],"150.25")
        self.assertEqual(result["by_platform"]["x"]["attributed_volume_usd"],"100.25")
        self.assertEqual(result["by_platform"]["facebook"]["attributed_completed_swaps"],0)

    def test_conflicting_duplicate_transaction_rejected(self):
        swaps = [
            {"swap_id":"1","session_id":"a","status":"completed","verified":True,"volume_usd":"1"},
            {"swap_id":"1","session_id":"a","status":"completed","verified":True,"volume_usd":"2"},
        ]
        with self.assertRaises(AnalyticsRejected):
            confirmed_swap_funnel([],swaps)

    def test_empty_data_is_genuine_zero_not_implied_fake(self):
        r = confirmed_swap_funnel([],[])
        self.assertEqual(r["verified_completed_swaps"],0)
        self.assertEqual(r["attributed_completed_swaps"],0)

    def test_unlinked_swap_not_attributed_by_date_or_platform(self):
        result = confirmed_swap_funnel(
            [{"session_id":"s1","utm_source":"instagram"}],
            [{"swap_id":"one","session_id":None,"status":"completed","verified":True,"volume_usd":"10"}],
        )
        self.assertEqual(result["unattributed_completed_swaps"],1)


if __name__=="__main__":
    unittest.main()
