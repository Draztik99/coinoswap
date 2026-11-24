"""Guard the future Facebook scheduler: hard-disabled until release approval."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/daily-rates.yml"


class ScheduledFacebookSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_scheduled_fb_job_is_hard_disabled(self):
        self.assertIn("  publish-facebook:", self.content)
        self.assertIn("if: ${{ false && github.event_name == 'schedule'", self.content)
        self.assertIn("needs.prepare.outputs.asset_generated == 'true'", self.content)
        self.assertIn("needs.prepare.result == 'success'", self.content)
        self.assertIn("environment: facebook-live", self.content)

    def test_only_newly_generated_current_day_sources_qualify(self):
        self.assertIn("asset_generated: ${{ steps.save.outputs.asset_generated }}", self.content)
        self.assertIn("asset_commit: ${{ steps.save.outputs.asset_commit }}", self.content)
        self.assertIn("echo \"asset_commit=$(git rev-parse HEAD)\" >> \"$GITHUB_OUTPUT\"", self.content)
        self.assertIn("ref: ${{ needs.prepare.outputs.asset_commit }}", self.content)
        self.assertIn("wait_for_rates_target.py", self.content)
        self.assertIn('publish_cli.py --publish --commit-sha "$SOURCE_SHA"', self.content)

    def test_verification_receipt_and_unique_tag_remain_required(self):
        self.assertIn("publication_receipt.py", self.content)
        self.assertIn('github-run-id "$GITHUB_RUN_ID"', self.content)
        self.assertIn('COINOSWAP_FB_PAGE_ACCESS_TOKEN: ${{ secrets.COINOSWAP_FB_PAGE_ACCESS_TOKEN }}', self.content)
        self.assertIn('COINOSWAP_METRICOOL_FB_DISABLED: "confirmed"', self.content)
        self.assertIn("git push origin HEAD:main", self.content)

    def test_instagram_metricool_untouched(self):
        self.assertNotIn("instagram_business_content_publish",self.content)
        self.assertNotIn("METRICOOL_API_KEY",self.content)
        self.assertNotIn("Metricool FB",self.content)

    def test_no_extra_schedule_or_trigger(self):
        self.assertEqual(self.content.count("  schedule:"),1)
        self.assertEqual(self.content.count("  workflow_dispatch:"),1)
        self.assertNotIn("pull_request_target:",self.content)


if __name__ == "__main__":
    unittest.main()
