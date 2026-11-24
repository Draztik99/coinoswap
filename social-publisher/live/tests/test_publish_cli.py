"""Dry-run safety checks for Facebook manual entrypoint; no network."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from publish_cli import main, APPROVAL_PHRASE


class ManualCLITests(unittest.TestCase):
    def test_default_no_post_never_loads_sources(self):
        with patch("publish_cli.fetch_pinned_pair") as fetch:
            with patch("sys.stdout",new_callable=io.StringIO) as out:
                result=main([])
        self.assertEqual(result,2)
        fetch.assert_not_called()
        self.assertIn("BLOCKED",out.getvalue())

    def test_all_approval_and_secret_gates_required(self):
        good = {"GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":"Draztik99/coinoswap",
                "APPROVAL_PHRASE":APPROVAL_PHRASE,
                "COINOSWAP_FB_LIVE_ENABLED":"true",
                "COINOSWAP_METRICOOL_FB_DISABLED":"confirmed",
                "COINOSWAP_FB_PAGE_ACCESS_TOKEN":"EAAG_FAKE_ONLY"}
        with patch("publish_cli.fetch_pinned_pair") as fetch:
            for key in good:
                env=dict(good)
                del env[key]
                with self.subTest(missing=key):
                    with patch("sys.stdout",new_callable=io.StringIO):
                        self.assertEqual(main(["--publish","--commit-sha","a"*40],env=env),2)
            fetch.assert_not_called()

    def test_bad_ref_rejected_before_any_github_or_facebook_call(self):
        env={"GITHUB_REF":"refs/heads/feature/direct-social-publishing"}
        with patch("publish_cli.fetch_pinned_pair") as fetch:
            with patch("sys.stdout",new_callable=io.StringIO):
                code=main(["--publish","--commit-sha","a"*40],env=env)
        self.assertEqual(code,2)
        fetch.assert_not_called()

    def test_missing_daily_asset_fails_without_post(self):
        from asset_reader import AssetRejected
        env={"GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":"Draztik99/coinoswap",
             "APPROVAL_PHRASE":APPROVAL_PHRASE,"COINOSWAP_FB_LIVE_ENABLED":"true",
             "COINOSWAP_METRICOOL_FB_DISABLED":"confirmed",
             "COINOSWAP_FB_PAGE_ACCESS_TOKEN":"EAAG_FAKE_ONLY"}
        with patch("publish_cli.fetch_pinned_pair",side_effect=AssetRejected("not today")):
            with patch("publish_cli.publish_once") as send:
                with patch("sys.stdout",new_callable=io.StringIO) as out:
                    code=main(["--publish","--commit-sha","a"*40],env=env)
        self.assertEqual(code,2)
        send.assert_not_called()
        self.assertNotIn("EAAG_FAKE_ONLY",out.getvalue())

    def test_workflow_manual_only_and_restricted_to_main(self):
        yaml = (Path(__file__).resolve().parents[3] / ".github/workflows/facebook-manual-publish.yml").read_text()
        self.assertIn("workflow_dispatch:",yaml)
        self.assertNotIn("schedule:",yaml)
        self.assertIn("github.ref == 'refs/heads/main'",yaml)
        self.assertIn("environment: facebook-live",yaml)
        self.assertIn("secrets.COINOSWAP_FB_PAGE_ACCESS_TOKEN",yaml)
        self.assertNotIn("pull_request_target",yaml)


if __name__=="__main__":
    unittest.main()
