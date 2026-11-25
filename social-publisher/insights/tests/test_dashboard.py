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

    def test_dashboard_prefers_evening_over_early_without_losing_history(self):
        directory=self.snapshots/"facebook"/"2026-11-24"
        directory.mkdir(parents=True)
        common={"platform":"facebook","provider_post_id":self.receipt["provider_post_id"],
                "date_sast":"2026-11-24",
                "published_at_sast":self.receipt["published_at_sast"],
                "public_url":self.receipt["public_url"]}
        early={**common,"collected_at_sast":"2026-11-25T16:05:00+02:00",
               "metrics":{name:None for name in FIELDS}}
        evening={**common,"collected_at_sast":"2026-11-25T19:05:00+02:00",
                 "metrics":{name:None for name in FIELDS}}
        early["metrics"]["views"]=1
        evening["metrics"]["views"]=12
        (directory/"2026-11-25-early.json").write_text(json.dumps(early))
        (directory/"2026-11-25-evening.json").write_text(json.dumps(evening))
        posts=load_posts(facebook_receipts=self.receipts,snapshots=self.snapshots)
        self.assertEqual(len(posts),1)
        self.assertEqual(posts[0]["metrics"]["views"],12)
        self.assertEqual(posts[0]["collected_at_sast"],"2026-11-25T19:05:00+02:00")

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

    def test_table_has_ten_cells_and_separate_metric_sync_from_post_link(self):
        from html.parser import HTMLParser

        class Rows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_body = False
                self.cells = []
                self.current_row = None
            def handle_starttag(self, tag, attrs):
                if tag == "tbody":
                    self.in_body = True
                elif self.in_body and tag == "tr":
                    self.current_row = []
                elif self.in_body and tag == "td" and self.current_row is not None:
                    self.current_row.append("")
                elif tag == "a" and self.current_row:
                    self.current_row[-1] += "[source]"
            def handle_endtag(self, tag):
                if tag == "tr" and self.current_row is not None:
                    self.cells.append(self.current_row)
                    self.current_row = None
                elif tag == "tbody":
                    self.in_body = False
            def handle_data(self, data):
                if self.in_body and self.current_row and data.strip():
                    self.current_row[-1] += data

        snapshots_dir = self.snapshots/"facebook"/"2026-11-24"
        snapshots_dir.mkdir(parents=True)
        data = {
            "platform": "facebook",
            "provider_post_id": self.receipt["provider_post_id"],
            "date_sast": "2026-11-24",
            "published_at_sast": self.receipt["published_at_sast"],
            "public_url": self.receipt["public_url"],
            "collected_at_sast": "2026-11-25T18:30:00+02:00",
            "metrics": {name: None for name in FIELDS},
        }
        (snapshots_dir/"2026-11-25.json").write_text(json.dumps(data))
        rendered = render(posts=load_posts(facebook_receipts=self.receipts,
                                          snapshots=self.snapshots), now=NOW)
        self.assertIn("<th>Metrics sync</th><th>Source</th>", rendered)
        rows = Rows()
        rows.feed(rendered)
        self.assertEqual(len(rows.cells), 1)
        self.assertEqual(len(rows.cells[0]), 10)
        self.assertIn("2026-11-25 18:30", rows.cells[0][8])
        self.assertNotIn("[source]", rows.cells[0][8])
        self.assertIn("[source]", rows.cells[0][9])
        self.assertIn("View post", rows.cells[0][9])

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

    def test_platform_and_confidence_panels_are_visible(self):
        posts=load_posts(facebook_receipts=self.receipts,snapshots=self.snapshots)
        markup=render(posts=posts,now=NOW)
        self.assertIn('id="channels"',markup)
        self.assertIn('id="insights"',markup)
        self.assertIn('id="performance"',markup)
        self.assertIn('id="methodology"',markup)
        self.assertIn('Reporting confidence',markup)
        self.assertIn('1 of 1 posts have metric snapshots' if posts[0].get('collected_at_sast') else '0 of 1 posts have metric snapshots',markup)
        self.assertIn('A reach comparison needs at least two posts',markup)
        self.assertNotIn('<script>',markup)

    def test_measured_reach_bars_are_based_only_on_reported_values(self):
        def row(platform,reach,day):
            return {'platform':platform,'date_sast':day,
                    'published_at_sast':day+'T12:10:00+02:00',
                    'public_url':'https://www.instagram.com/p/test/',
                    'collected_at_sast':day+'T14:10:00+02:00',
                    'metrics':{name:(reach if name=='reach' else None) for name in FIELDS}}
        posts=[row('instagram',10,'2026-11-23'),row('instagram',5,'2026-11-22')]
        page=render(posts=posts,now=NOW)
        self.assertIn('width:100.0%',page)
        self.assertIn('width:50.0%',page)
        self.assertIn('2 have measured reach',page)
        self.assertNotIn('A reach comparison needs at least two posts',page)

    def test_source_health_reports_missing_metrics_without_fabricating_reach(self):
        posts=load_posts(facebook_receipts=self.receipts,snapshots=self.snapshots)
        rendered=render(posts=posts,now=NOW)
        self.assertIn('id="health"',rendered)
        self.assertIn('NO METRICS',rendered)
        self.assertIn('NO TRACKED POSTS',rendered)
        self.assertIn('0/1 tracked posts have reach',rendered)
        self.assertIn('Tracked last 7 days: 1',rendered)
        self.assertIn('Tracked last 30 days: 1',rendered)
        self.assertIn('This does not prove no posts were published.',rendered)

    def test_source_health_reports_stale_snapshot(self):
        directory=self.snapshots/"facebook"/"2026-11-24"
        directory.mkdir(parents=True)
        record={"platform":"facebook","provider_post_id":self.receipt["provider_post_id"],
                "date_sast":"2026-11-24",
                "published_at_sast":self.receipt["published_at_sast"],
                "public_url":self.receipt["public_url"],
                "collected_at_sast":"2026-11-24T19:54:21+02:00",
                "metrics":{name:None for name in FIELDS}}
        (directory/"2026-11-24.json").write_text(json.dumps(record))
        late=datetime.fromisoformat("2026-11-27T21:00:00+02:00")
        rendered=render(posts=load_posts(facebook_receipts=self.receipts,
                                         snapshots=self.snapshots),now=late)
        self.assertIn('STALE SNAPSHOT',rendered)
        self.assertIn('0/1 tracked posts have reach',rendered)

    def test_zero_post_dashboard_is_transparent(self):
        d=build(receipts=self.root/"absent",snapshots=self.snapshots,output=self.out,now=NOW)
        self.assertEqual(d["verified_posts"],0)
        self.assertIn("No verified posts yet",self.out.read_text())

if __name__=="__main__":
    unittest.main()
