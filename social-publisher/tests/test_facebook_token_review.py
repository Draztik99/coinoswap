"""Offline Meta access-token lifecycle contract tests; no tokens or network."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facebook_token_review import review_token_metadata, MIN_REMAINING_SECONDS

NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)
APP_ID = "1234567890"
TOKEN_SENTINEL = "SENSITIVE_FAKE_TOKEN_NOT_REAL"


def response(**overrides):
    base = {
        "is_valid": True, "app_id": APP_ID, "scopes": [
            "pages_manage_posts", "pages_read_engagement", "pages_show_list",
        ],
        "expires_at": int((NOW + timedelta(days=45)).timestamp()),
        "data_access_expires_at": int((NOW + timedelta(days=40)).timestamp()),
    }
    base.update(overrides)
    return {"data": base, "debug_token": TOKEN_SENTINEL}


class TokenReviewTests(unittest.TestCase):
    def review(self, meta, **kw):
        return review_token_metadata(meta, expected_app_id=APP_ID, now=NOW, **kw)

    def test_valid_metadata_never_authorizes_publishing(self):
        result = self.review(response())
        self.assertEqual(result.status, "VALIDITY_WINDOW_OK")
        self.assertFalse(result.ready_for_live_publishing)
        self.assertGreater(result.seconds_until_expiry, MIN_REMAINING_SECONDS)
        self.assertNotIn(TOKEN_SENTINEL, repr(result))

    def test_invalid_token_and_wrong_app(self):
        self.assertEqual(self.review(response(is_valid=False)).status, "INVALID")
        self.assertEqual(self.review(response(app_id="999")).status, "WRONG_APP")

    def test_missing_required_scopes(self):
        result = self.review(response(scopes=["pages_show_list"]))
        self.assertEqual(result.status, "MISSING_SCOPES")
        self.assertEqual(result.missing_scopes,
                         ("pages_manage_posts", "pages_read_engagement"))

    def test_expiring_soon(self):
        expires = int((NOW + timedelta(hours=4)).timestamp())
        result = self.review(response(expires_at=expires))
        self.assertEqual(result.status, "EXPIRING_SOON")
        self.assertFalse(result.ready_for_live_publishing)

    def test_expired(self):
        result = self.review(response(expires_at=int((NOW - timedelta(seconds=1)).timestamp())))
        self.assertEqual(result.status, "EXPIRED")

    def test_nonexpiring_report_is_manual_review(self):
        self.assertEqual(self.review(response(expires_at=0)).status, "REVIEW_REQUIRED")

    def test_missing_data_access_expiry_requires_review(self):
        data = response()["data"]
        del data["data_access_expires_at"]
        self.assertEqual(self.review({"data": data}).status, "REVIEW_REQUIRED")

    def test_data_access_expiring_and_expired(self):
        for delta, status in [(-1, "DATA_ACCESS_EXPIRED"), (3600, "DATA_ACCESS_EXPIRING_SOON")]:
            with self.subTest(status=status):
                stamp = int(NOW.timestamp()) + delta
                self.assertEqual(self.review(response(data_access_expires_at=stamp)).status, status)

    def test_untrusted_response_never_leaks_errors_or_secrets(self):
        for bad in ({}, {"error": {"message": TOKEN_SENTINEL}},
                    {"data": {"access_token": TOKEN_SENTINEL}},
                    {"data": []}, None):
            result = self.review(bad)
            self.assertFalse(result.ready_for_live_publishing)
            self.assertNotIn(TOKEN_SENTINEL, repr(result))

    def test_bad_clock_and_metadata_blocked(self):
        self.assertEqual(
            review_token_metadata(response(), expected_app_id="", now=NOW).status,
            "INVALID_CONFIGURATION",
        )
        self.assertEqual(
            review_token_metadata(response(), expected_app_id=APP_ID, now=datetime.now()).status,
            "INVALID_CONFIGURATION",
        )
        for field, value in [("scopes", "pages_manage_posts"), ("expires_at", True),
                             ("expires_at", "12345"), ("data_access_expires_at", "123")]:
            with self.subTest(field=field):
                self.assertEqual(self.review(response(**{field: value})).status, "UNVERIFIED")

    def test_no_expiration_credentials_in_output(self):
        data = response()["data"]
        data["access_token"] = TOKEN_SENTINEL
        data["user_id"] = "9876543210"
        result = self.review({"data": data})
        self.assertNotIn(TOKEN_SENTINEL, str(result))
        self.assertNotIn("9876543210", str(result))


if __name__ == "__main__":
    unittest.main()
