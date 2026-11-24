"""Offline Facebook shadow tests: absolutely no social publishing or tokens."""
import io
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from asset_reader import AssetRejected, ValidatedAsset
from facebook_shadow import (
    build_facebook_shadow_preview, preview_pinned_asset, main,
)

COMMIT = "a" * 40
IMAGE_HASH = "c" * 64
NOW = datetime.fromisoformat("2026-11-23T14:49:00+02:00")


def valid_asset():
    return ValidatedAsset(
        date_sast="2026-11-23",
        target_sast=NOW.isoformat(timespec="seconds"),
        image_sha256=IMAGE_HASH,
        caption="CoinoSwap BTC ETH XMR daily rates",
        display_prices={"BTC": "$1.00", "ETH": "$2.00", "XMR": "$3.00"},
    )


class FacebookShadowTests(unittest.TestCase):
    def test_metricool_active_blocks_all_live_posts(self):
        p = build_facebook_shadow_preview(valid_asset(), pinned_main_commit=COMMIT)
        self.assertEqual(p.status, "BLOCKED_METRICOOL")
        self.assertEqual(p.published_posts_created, 0)
        self.assertEqual(p.page_id, "108130358772133")
        self.assertIn("Metricool", p.reason)
        self.assertEqual(p.intended_api_operation, "page_photo")
        self.assertTrue(p.validated_image_url.endswith(
            "/docs/daily-rates/2026-11-23.png"))

    def test_even_when_metricool_inactive_no_live_post_capability(self):
        p = build_facebook_shadow_preview(
            valid_asset(), pinned_main_commit=COMMIT, metricool_active=False)
        self.assertEqual(p.status, "SHADOW_ONLY")
        self.assertEqual(p.published_posts_created, 0)
        self.assertIn("no explicit", p.reason)

    def test_bad_or_unpinned_sources_rejected(self):
        for sha in ("main", "abc", "0" * 39, "g" * 40, ""):
            with self.subTest(sha=sha):
                with self.assertRaises(AssetRejected):
                    build_facebook_shadow_preview(valid_asset(), pinned_main_commit=sha)
        with self.assertRaises(AssetRejected):
            build_facebook_shadow_preview(None, pinned_main_commit=COMMIT)

    def test_invalid_asset_digest_or_target_rejected(self):
        a = valid_asset()
        from dataclasses import replace
        for invalid in (replace(a, image_sha256="invalid"),
                        replace(a, target_sast="2026-11-22T14:49:00+02:00")):
            with self.assertRaises(AssetRejected):
                build_facebook_shadow_preview(invalid, pinned_main_commit=COMMIT)

    def test_invalid_metricool_status_rejected(self):
        with self.assertRaises(AssetRejected):
            build_facebook_shadow_preview(valid_asset(), pinned_main_commit=COMMIT, metricool_active=None)

    def test_pinned_asset_validator_invoked_before_preview(self):
        with patch("facebook_shadow.fetch_pinned_pair", return_value=(b"json", b"png")) as fetch:
            with patch("facebook_shadow.validate_asset_pair", return_value=valid_asset()) as validate:
                preview = preview_pinned_asset(pinned_main_commit=COMMIT, at_sast=NOW)
        self.assertEqual(preview.status, "BLOCKED_METRICOOL")
        fetch.assert_called_once_with(commit_sha=COMMIT, date_sast="2026-11-23")
        validate.assert_called_once_with(b"json", b"png", now=NOW)

    def test_validation_failure_never_produces_preview(self):
        with patch("facebook_shadow.fetch_pinned_pair", return_value=(b"x", b"y")):
            with patch("facebook_shadow.validate_asset_pair", side_effect=AssetRejected("stale")):
                with self.assertRaisesRegex(AssetRejected, "stale"):
                    preview_pinned_asset(pinned_main_commit=COMMIT, at_sast=NOW)

    def test_cli_outputs_no_token_and_zero_posts(self):
        with patch("facebook_shadow.preview_pinned_asset", return_value=build_facebook_shadow_preview(valid_asset(), pinned_main_commit=COMMIT)):
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["--commit-sha", COMMIT])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["published_posts_created"], 0)
        self.assertNotIn("access_token", out.getvalue())
        self.assertNotIn("Bearer", out.getvalue())

    def test_cli_fail_closed_when_image_invalid(self):
        with patch("facebook_shadow.preview_pinned_asset", side_effect=AssetRejected("asset stale")):
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["--commit-sha", COMMIT])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "BLOCKED_VALIDATION")


if __name__ == "__main__":
    unittest.main()
