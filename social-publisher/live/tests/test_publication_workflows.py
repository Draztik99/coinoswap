"""Guard future direct Facebook workflows against accidental automatic posts."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "docs/daily-rates/2026-11-24.json"
HIST = ROOT / "docs/daily-rates/facebook-publications/2026-11-24.json"

sys.path.insert(0, str(ROOT / "social-publisher/live"))
from publication_receipt import verified_receipt


class HandoverContracts(unittest.TestCase):
    def test_historical_success_receipt_matches_the_actual_source(self):
        audit = json.loads(SRC.read_text(encoding="utf-8"))
        receipt = json.loads(HIST.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "PUBLISHED")
        self.assertEqual(receipt["platform"], "facebook")
        self.assertEqual(receipt["page_id"], "108130358772133")
        self.assertEqual(receipt["date_sast"], audit["date_sast"])
        self.assertEqual(receipt["source_image_sha256"], audit["image"]["sha256"])
        self.assertEqual(audit["status"], "VALIDATED")
        self.assertEqual(audit["approval_state"], "NOT_PUBLISHED")
        expected = verified_receipt(
            {"status": "PUBLISHED", "reason": "Facebook Page photo independently verified",
             "page_id": receipt["page_id"], "provider_post_id": receipt["provider_post_id"],
             "public_url": receipt["public_url"], "reservation_tag": receipt["reservation_tag"]},
            audit, source_commit=receipt["source_commit"],
            github_run_id=receipt["github_run_id"],
            at_sast=__import__("datetime").datetime.fromisoformat(receipt["published_at_sast"]),
        )
        self.assertEqual(expected, receipt)

    def test_publish_workflows_are_manual_only_and_gate_facebook(self):
        for name in ("facebook-manual-publish.yml","facebook-fresh-daily-rates-manual.yml"):
            with self.subTest(name=name):
                src=(ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
                self.assertIn("workflow_dispatch:",src)
                self.assertNotIn("\n  schedule:",src)
                self.assertNotIn("\n  push:",src)
                self.assertIn("github.ref == 'refs/heads/main'",src)
                self.assertIn("environment: facebook-live",src)
                self.assertIn("inputs.metricool_facebook_disabled == true",src)
                self.assertIn("secrets.COINOSWAP_FB_PAGE_ACCESS_TOKEN",src)
                self.assertIn("publication_receipt.py",src)
                self.assertIn("github-run-id",src)
                self.assertIn("coinoswap_fb_verified_result.json",src)
                self.assertIn("git push origin HEAD:main",src)
                self.assertNotIn("vars.COINOSWAP_FB_LIVE_ENABLED",src)
                self.assertNotIn("vars.COINOSWAP_METRICOOL_FB_DISABLED",src)

    def test_daily_generator_manual_emergency_matches_user_input(self):
        source = (ROOT / ".github/workflows/daily-rates.yml").read_text()
        self.assertEqual(source.count("inputs.emergency == true"),2)
        self.assertNotIn("github.event_name == 'workflow_dispatch' && 'true' || 'false'",source)

    def test_live_workflows_cannot_publish_instagram(self):
        for name in ("facebook-manual-publish.yml","facebook-fresh-daily-rates-manual.yml"):
            src=(ROOT / ".github/workflows" / name).read_text()
            self.assertNotIn("instagram_business_content_publish",src)
            self.assertNotIn("METRICOOL_API_KEY",src)
            self.assertNotIn("secrets.INSTAGRAM",src)


if __name__ == "__main__":
    unittest.main()
