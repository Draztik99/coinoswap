"""No-live gate, Metricool cross-publication guard and secret-safe alerts."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alerts import publication_alert, redact_failure_detail
from launch_gate import evaluate_release_gate
from ledger import PublicationLedger, LedgerError

HASH = "9"*64
DATE = "2026-11-23"


class SafeguardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = PublicationLedger(Path(self.tmp.name)/"local.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_platforms_closed_by_default(self):
        for p in ("x","facebook","instagram"):
            self.assertFalse(evaluate_release_gate(p).ready_for_further_live_integration)

    def test_metricool_overlap_blocks_fb_and_ig_even_when_approved(self):
        for p in ("facebook","instagram"):
            decision = evaluate_release_gate(
                p, explicitly_approved=True,
                production_credentials_verified=True, authoritative_shared_ledger=True,
                metricool_active=True, external_publication_checked=True,
                verified_shadows=True,
            )
            self.assertFalse(decision.ready_for_further_live_integration)
            self.assertIn("Metricool",decision.reason)

    def test_approval_alone_cannot_enable_live_api(self):
        self.assertFalse(evaluate_release_gate("x",explicitly_approved=True).ready_for_further_live_integration)

    def test_all_prerequisites_only_yield_readiness(self):
        result = evaluate_release_gate(
            "x",explicitly_approved=True,production_credentials_verified=True,
            authoritative_shared_ledger=True,metricool_active=False,
            external_publication_checked=True,verified_shadows=True,
        )
        self.assertTrue(result.ready_for_further_live_integration)
        self.assertIn("separate live deployment",result.reason)

    def test_external_metricool_fb_receipt_prevents_duplicate(self):
        self.assertTrue(self.ledger.adopt_external_receipt(
            "facebook",DATE,"daily_rates",HASH,source="metricool",
            provider_post_id="111",public_url="https://facebook.com/123/posts/111"))
        self.assertFalse(self.ledger.reserve("facebook",DATE,"daily_rates",HASH,"retry-1"))
        self.assertEqual(self.ledger.get("facebook",DATE,"daily_rates")["state"],"PUBLISHED")

    def test_metricool_instagram_receipt_prevents_duplicate(self):
        self.assertTrue(self.ledger.adopt_external_receipt(
            "instagram",DATE,"daily_rates",HASH,source="metricool",
            provider_post_id="ig-media",public_url="https://www.instagram.com/p/example/"))
        self.assertFalse(self.ledger.reserve("instagram",DATE,"daily_rates",HASH,"retry-1"))

    def test_metricool_does_not_block_new_x_slot(self):
        self.ledger.adopt_external_receipt(
            "facebook",DATE,"daily_rates",HASH,source="metricool",
            provider_post_id="111",public_url="https://facebook.com/123/posts/111")
        self.assertTrue(self.ledger.reserve("x",DATE,"daily_rates",HASH,"x-req"))

    def test_external_receipt_cannot_overwrite_direct_reservation(self):
        self.ledger.reserve("facebook",DATE,"daily_rates",HASH,"direct")
        self.assertFalse(self.ledger.adopt_external_receipt(
            "facebook",DATE,"daily_rates",HASH,source="metricool",
            provider_post_id="111",public_url="https://facebook.com/123/posts/111"))

    def test_external_receipt_rejects_wrong_origin_and_url(self):
        with self.assertRaises(LedgerError):
            self.ledger.adopt_external_receipt(
                "x",DATE,"daily_rates",HASH,source="metricool",
                provider_post_id="1",public_url="https://x.com/a/status/1")
        with self.assertRaises(LedgerError):
            self.ledger.adopt_external_receipt(
                "facebook",DATE,"daily_rates",HASH,source="metricool",
                provider_post_id="1",public_url="https://example.com/fb/1")

    def test_alert_never_prints_tokens(self):
        sample={
            "platform":"x","date_sast":DATE,"state":"UNKNOWN",
            "last_error":"upstream Bearer abc123 access_token=verysecret api_key=abcde1",
        }
        alert=publication_alert(sample)
        self.assertEqual(alert["severity"],"CRITICAL")
        self.assertNotIn("abc123",str(alert))
        self.assertNotIn("verysecret",str(alert))
        self.assertNotIn("abcde1",str(alert))

    def test_no_alert_for_healthy_published(self):
        self.assertIsNone(publication_alert({"state":"PUBLISHED"}))


if __name__=="__main__":
    unittest.main()
