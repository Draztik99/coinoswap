"""Safety policy for the development-only GitHub Actions workflow.

A future edit must not silently schedule posts, access credentials or broaden
the branch where the isolated shadow checks run.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "direct-social-tests.yml"


class WorkflowIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_only_feature_branch_is_eligible(self):
        wf = self.workflow
        self.assertIn("branches:\n      - feature/direct-social-publishing", wf)
        self.assertIn("if: github.ref == 'refs/heads/feature/direct-social-publishing'", wf)
        self.assertNotRegex(wf, r"(?m)^\s+- main\s*$")
        self.assertNotIn("pull_request:", wf)
        self.assertNotIn("pull_request_target:", wf)

    def test_not_scheduled_and_no_credentials(self):
        wf = self.workflow
        self.assertNotRegex(wf, r"(?m)^\s+schedule:\s*$")
        self.assertNotIn("repository_dispatch:", wf)
        self.assertNotIn("secrets.", wf)
        # The only environment data is for a disposable CI PostgreSQL fixture.
        self.assertIn("COINOSWAP_TEST_PG_DSN:", wf)
        self.assertNotIn("COINOSWAP_FB_PAGE_ACCESS_TOKEN", wf)
        self.assertNotIn("META_APP_SECRET", wf)
        self.assertNotIn("METRICOOL_API_KEY", wf)
        self.assertNotIn("environment:", wf)
        self.assertNotIn("workflow_run:", wf)
        self.assertNotRegex(wf, r"(?m)^\s+uses:.*(facebook|metricool|instagram)", wf)

    def test_read_only_permissions_and_offline_test_command(self):
        wf = self.workflow
        self.assertIn("permissions:\n  contents: read", wf)
        self.assertNotRegex(wf, r"(?m)^\s+\w+-?\w*: write\s*$")
        self.assertIn("python -m unittest discover -s social-publisher/tests -v", wf)
        self.assertIn("NO POST", wf)
        self.assertNotRegex(wf, r"(?im)^\s+run:.*\b(?:publish|deploy|curl|facebook|metricool)\b", wf)

    def test_node24_compatible_actions(self):
        wf = self.workflow
        for action in ("actions/checkout@v6", "actions/setup-python@v6",
                       "actions/upload-artifact@v6"):
            with self.subTest(action=action):
                self.assertIn(action, wf)
        self.assertNotRegex(wf, r"actions/(?:checkout|setup-python|upload-artifact)@v[1-5]\b")


if __name__ == "__main__":
    unittest.main()
