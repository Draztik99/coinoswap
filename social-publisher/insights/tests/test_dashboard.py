"""Offline dashboard regression tests: no fabricated social or swap data."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard import build,render,load_posts
from model import FIELDS,SAST,AnalyticsError

NOW=datetime.fromisoformat("2026-11-25T21:00:00+02:00")

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.receipts=self.root/"fb"
        self.receipts.mkdir()
        self.snapshots=self.root/"snapshots"
        self.snapshots.mkdir()
        self.out=self.root/"index.html"
        self.receipt={"status":"PUBLISHED","platform":"facebook","verification":"META_PAGE_PHOTO_READBACK",
                      "page_id":"108130358772133","date_sast":"2026-11-24",
                      "provider_post_id":"108130358772133_1137307232527711",
                      "public_url":"https://www.facebook.com/photo.php?fbid=1137307215861046",
                      "published_at_sast":"2026-11-24T19:19:05+02:00"}
        (self.receipts/"2026-11-24.json").write_text(json.dumps(self.receipt))

    def test_verified_post_without_metrics_is_pending(self):
        rows=load_posts(facebook_receipts=self.receipts,snapshots=self.snapshots)
        self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0]["metrics"]["reach"])
        html=render(posts=rows,now=NOW)
        self.assertIn("N/A",html)
        self.assertIn("Verified Facebook posts",html)
        self.assertNotIn("US$ 0.00",html)

    def test_metrics_snapshots_upgrade_without_losing_receipt(self):
        directory=self.snapshots/"facebook"/"2026-11-24"
        directory.mkdir(parents=True)
        latest={"platform":"facebook","provider_post_id":self.receipt["provider_post_id"],
                "date_sast":"2026-11-24",
                "published_at_sast":self.receipt["published_at_sast"],
                "public_url":self.receipt["public_url"],
                "collected_at_sast":"2026-11-25T18:30:00+02:00",
                "metrics":{name:None for name in FIELDS}}
        latest["metrics"]["comments"]=0
        (directory/"2026-11-25.json").write_text(json.dumps(latest))
        summary=build(receipts=self.receipts,snapshots=self.snapshots,output=self.out,now=NOW)
        self.assertEqual(summary["facebook_posts"],1)
        self.assertIn("N/A",self.out.read_text())
        self.assertIn(">0</td>",self.out.read_text())

    def test_reject_metric_record_for_wrong_post(self):
        directory=self.snapshots/"facebook"/"2026-11-24"
        directory.mkdir(parents=True)
        latest={"platform":"facebook","provider_post_id":self.receipt["provider_post_id"],
                "date_sast":"2026-11-23","published_at_sast":self.receipt["published_at_sast"],
                "public_url":self.receipt["public_url"],
                "collected_at_sast":"2026-11-25T18:30:00+02:00","metrics":{name:None for name in FIELDS}}
        (directory/"2026-11-25.json").write_text(json.dumps(latest))
        with self.assertRaises(AnalyticsError):
            load_posts(facebook_receipts=self.receipts,snapshots=self.snapshots)

    def test_untrusted_post_link_is_html_escaped(self):
        row={"platform":"instagram","date_sast":"2026-11-22",
             "published_at_sast":"2026-11-22T12:10:00+02:00",
             "public_url":"https://www.instagram.com/p/x/?a=<script>alert(1)</script>",
             "metrics":{name:None for name in FIELDS},"collected_at_sast":None}
        html=render(posts=[row],now=NOW)
        self.assertNotIn("<script>",html)
        self.assertIn("&lt;script&gt;",html)

    def test_dashboard_identifies_stale_observations(self):
        directory=self.snapshots/"facebook"/"2026-11-24"
        directory.mkdir(parents=True)
        record={"platform":"facebook","provider_post_id":self.receipt["provider_post_id"],
                "date_sast":"2026-11-24","published_at_sast":self.receipt["published_at_sast"],
                "public_url":self.receipt["public_url"],
                "collected_at_sast":"2026-11-24T19:54:21+02:00",
                "metrics":{name:None for name in FIELDS}}
        (directory/"2026-11-24.json").write_text(json.dumps(record))
        late=datetime.fromisoformat("2026-11-27T21:00:00+02:00")
        posts=load_posts(facebook_receipts=self.receipts,snapshots=self.snapshots)
        result=render(posts=posts,now=late)
        self.assertIn("STALE",result)
        self.assertIn("Facebook latest metrics:",result)
        self.assertIn("Instagram latest metrics: No metrics collected",result)

    def test_zero_post_dashboard_is_transparent(self):
        d=build(receipts=self.root/"absent",snapshots=self.snapshots,output=self.out,now=NOW)
        self.assertEqual(d["verified_posts"],0)
        self.assertIn("No verified posts yet",self.out.read_text())

if __name__=="__main__":
    unittest.main()
