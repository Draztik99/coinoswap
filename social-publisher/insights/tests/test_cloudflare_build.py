"""Offline deployment safety regression tests; no Cloudflare or social API calls."""
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(DIR))
from cloudflare_build import build, access_release_ready, csv_report, _safe_csv

class CloudflareDeployTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.out=self.root/"dist"
        self.now=datetime.fromisoformat("2026-11-24T20:15:00+02:00")

    def test_zero_config_is_locked_with_no_snapshot_files(self):
        r=build(root=self.root,output=self.out,environ={},at=self.now)
        self.assertEqual(r["status"],"LOCKED_PLACEHOLDER")
        self.assertEqual(r["data_files_exported"],0)
        self.assertFalse((self.out/"reports").exists())
        self.assertNotIn("2026-11-24", (self.out/"index.html").read_text())
        self.assertIn("no-store", (self.out/"_headers").read_text())
        self.assertIn("Disallow: /",(self.out/"robots.txt").read_text())

    def test_access_flag_without_main_is_still_locked(self):
        for branch in ("feature/foo","preview","",None):
            with self.subTest(branch=branch):
                env={"COINOSWAP_TEAM_ACCESS_VERIFIED":"true"}
                if branch is not None:env["CF_PAGES_BRANCH"]=branch
                self.assertFalse(access_release_ready(env))
                r=build(root=self.root,output=self.out,environ=env,at=self.now)
                self.assertEqual(r["status"],"LOCKED_PLACEHOLDER")

    def test_wrong_flag_value_does_not_unlock(self):
        for val in ("TRUE","1","yes","false"," true ",""):
            self.assertFalse(access_release_ready(
                {"CF_PAGES_BRANCH":"main","COINOSWAP_TEAM_ACCESS_VERIFIED":val}
            ))

    def test_release_only_exports_whitelisted_aggregate_data(self):
        receipt_dir=self.root/"docs/daily-rates/facebook-publications"
        receipt_dir.mkdir(parents=True)
        receipt={
            "platform":"facebook", "status":"PUBLISHED",
            "verification":"META_PAGE_PHOTO_READBACK",
            "page_id":"108130358772133",
            "date_sast":"2026-11-24",
            "provider_post_id":"108130358772133_1137307232527711",
            "public_url":"https://www.facebook.com/photo.php?fbid=1137307215861046",
            "published_at_sast":"2026-11-24T19:19:05+02:00",
        }
        (receipt_dir/"2026-11-24.json").write_text(json.dumps(receipt))
        # Simulate a private-looking file in repo; it MUST NOT be exported.
        (self.root/"private.txt").write_text("PRIVATE_TOKEN_NEVER_EXPORTED")
        r=build(root=self.root,output=self.out,
                environ={"CF_PAGES_BRANCH":"main",
                         "COINOSWAP_TEAM_ACCESS_VERIFIED":"true"},
                at=self.now)
        self.assertEqual(r["status"],"PRIVATE_DASHBOARD_ARTIFACT_BUILT")
        self.assertEqual(r["posts"],1)
        self.assertEqual(len(r["files"]),4)
        csv_data=(self.out/"reports/post-performance.csv").read_text()
        self.assertIn("108130358772133_1137307232527711",csv_data)
        self.assertIn("N/A",csv_data)
        self.assertNotIn("PRIVATE_TOKEN_NEVER_EXPORTED",csv_data)
        html=(self.out/"index.html").read_text()
        self.assertIn("Download post report",html)
        self.assertNotIn("PRIVATE_TOKEN_NEVER_EXPORTED",html)
        self.assertNotIn("access_token",html)

    def test_revoking_access_acknowledgement_removes_previous_export(self):
        build(root=self.root,output=self.out,
              environ={"CF_PAGES_BRANCH":"main",
                       "COINOSWAP_TEAM_ACCESS_VERIFIED":"true"},at=self.now)
        r=build(root=self.root,output=self.out,environ={},at=self.now)
        self.assertEqual(r["status"],"LOCKED_PLACEHOLDER")
        self.assertFalse((self.out/"reports").exists())

    def test_formula_injection_is_escaped(self):
        for formula in ("=1+1","+SUM(1,2)","-5","@cmd","   =2+2"):
            self.assertTrue(_safe_csv(formula).startswith("'"))

    def test_only_dist_is_deletable(self):
        with self.assertRaises(ValueError):
            build(root=self.root,output=self.root,environ={})
        with self.assertRaises(ValueError):
            build(root=self.root,output=self.root/"repo",environ={})

if __name__=="__main__":
    unittest.main()
