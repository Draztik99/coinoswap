"""Release contract for user-authorized recurring Facebook Daily Rates.

Source generation stays randomized over the seven SAST half-hour slots;
Facebook sends only after fresh source commit on a real scheduled event.
All tests are source inspections with no secrets and no network.
"""
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-rates.yml"
sys.path.insert(0, str(ROOT / "daily-rates"))
from posting_slots import SLOTS, slot_for_date, expected_prepare_time


class RecurringFacebookSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WORKFLOW.read_text(encoding="utf-8")
        cls.job = cls.content.split("\n  publish-facebook:\n", 1)[1]

    def test_production_job_now_enabled_only_for_approved_scheduled_event(self):
        self.assertIn("  publish-facebook:", self.content)
        self.assertNotIn("false && github.event_name == 'schedule'", self.job)
        self.assertIn("github.ref == 'refs/heads/main'", self.job)
        self.assertIn("github.event_name == 'schedule'", self.job)
        self.assertIn("vars.COINOSWAP_FB_DAILY_PAUSED != 'true'", self.job)
        self.assertIn("needs.prepare.outputs.asset_generated == 'true'", self.job)
        self.assertIn("needs.prepare.result == 'success'", self.job)
        self.assertIn("needs: prepare", self.job)
        self.assertIn("environment: facebook-live", self.job)
        self.assertIn("APPROVAL_PHRASE:", self.job)

    def test_balanced_randomized_times_and_preparation_offset(self):
        self.assertEqual(SLOTS, ((11,30),(12,0),(12,30),(13,0),
                                 (13,30),(14,0),(14,30)))
        for monday in (date(2026, 11, 23), date(2026, 11, 30),
                       date(2026, 12, 7), date(2026, 12, 14)):
            times = [slot_for_date(monday + timedelta(days=i)) for i in range(7)]
            self.assertEqual(set(times), set(SLOTS))
            self.assertEqual(len(times), 7)
            for i, target in enumerate(times):
                prep = expected_prepare_time(monday + timedelta(days=i))
                self.assertEqual(prep[0]*60+prep[1],target[0]*60+target[1]-4)

    def test_no_manual_dispatch_or_push_can_send_a_scheduled_post(self):
        self.assertEqual(self.content.count("  schedule:"), 1)
        self.assertEqual(self.content.count("  workflow_dispatch:"), 1)
        self.assertNotIn("pull_request_target:", self.content)
        self.assertNotIn("\n  push:", self.content)
        self.assertIn("github.event_name == 'schedule'", self.job)

    def test_fresh_immutable_source_mandatory(self):
        self.assertIn("asset_generated: ${{ steps.save.outputs.asset_generated }}", self.content)
        self.assertIn("asset_commit: ${{ steps.save.outputs.asset_commit }}", self.content)
        self.assertIn('echo "asset_commit=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"', self.content)
        self.assertIn("ref: ${{ needs.prepare.outputs.asset_commit }}", self.job)
        self.assertIn("wait_for_rates_target.py", self.job)
        self.assertIn('publish_cli.py --publish --commit-sha "$SOURCE_SHA"', self.job)

    def test_secrets_are_restricted_to_meta_job(self):
        self.assertIn("COINOSWAP_FB_PAGE_ACCESS_TOKEN: ${{ secrets.COINOSWAP_FB_PAGE_ACCESS_TOKEN }}",self.job)
        self.assertIn('COINOSWAP_METRICOOL_FB_DISABLED: "confirmed"',self.job)
        self.assertNotIn("METRICOOL_API_KEY",self.content)
        self.assertNotIn("instagram_business_content_publish",self.content)

    def test_tag_reservation_and_verified_receipt_present(self):
        self.assertIn("publication_receipt.py", self.job)
        self.assertIn('github-run-id "$GITHUB_RUN_ID"',self.job)
        self.assertIn('git push origin HEAD:main',self.job)
        self.assertIn("Do not retry publishing",self.job)
        # Git retry is for the receipt only, after the independent FB POST.
        self.assertLess(self.job.index('publish_cli.py --publish'),self.job.index('for attempt in 1 2 3'))
        self.assertEqual(self.job.count('publish_cli.py --publish'),1)

    def test_publish_never_starts_without_source_commit(self):
        self.assertIn("if: ${{ github.ref == 'refs/heads/main' && github.event_name == 'schedule'",self.job)
        self.assertIn("needs.prepare.outputs.asset_generated == 'true'",self.job)

    def test_ig_watchers_remain_outside_github(self):
        self.assertNotIn("instagram_business_content_publish",self.job.lower())
        self.assertNotIn("metricool.com",self.job.lower())


if __name__ == "__main__":
    unittest.main()
