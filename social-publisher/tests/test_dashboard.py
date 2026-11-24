"""Ensure dashboard never invents data, double-counts or exposes HTML."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard import DashboardRejected, render_dashboard


class DashboardTests(unittest.TestCase):
    def test_empty_dashboard_says_na_not_zero(self):
        html = render_dashboard()
        self.assertIn("N/A",html)
        self.assertIn("Not connected",html)
        self.assertIn("SHADOW / NO LIVE DATA",html)
        self.assertNotIn("999,999",html)

    def test_explicit_zero_is_not_missing(self):
        html = render_dashboard({
            "website":{"sessions":0}, "swaps":{"verified_completed":0,"attributed_completed":0,"volume_usd":"0"},
            "platforms":{"x":{"impressions":0,"views":None,"engagements":0,"link_clicks":0,"engagement_rate":0}}
        })
        self.assertIn("US$ 0.00",html)
        self.assertIn("0.00%",html)

    def test_html_injection_is_escaped(self):
        html = render_dashboard({
            "as_of_sast":'<script>alert("x")</script>',
            "platforms":{"x":{"status":'<img src=x onerror=alert(1)>'}}
        })
        self.assertNotIn("<script>",html)
        self.assertNotIn("<img src=x",html)
        self.assertIn("&lt;script&gt;",html)

    def test_invalid_negative_metric_is_rejected(self):
        with self.assertRaises(DashboardRejected):
            render_dashboard({"website":{"sessions":-1}})

    def test_unverified_nonfinite_volume_rejected(self):
        with self.assertRaises(DashboardRejected):
            render_dashboard({"swaps":{"volume_usd":"NaN"}})

    def test_platforms_show_separate_views_and_impressions(self):
        html=render_dashboard({"platforms":{"x":{"impressions":50},"instagram":{"views":30}}})
        self.assertIn("50",html)
        self.assertIn("30",html)
        self.assertIn("Per-platform performance",html)


if __name__=="__main__":
    unittest.main()
