"""Mock Meta GETs without external network or access tokens."""
import io
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facebook_page_readback import (
    PAGE_POSTS_URL, GRAPH_ME_URL, TOKEN_ENV, MAX_PAGE_RESPONSE,
    _get_json, audit_page_published_posts, main,
)
from facebook_page_auth import COINOSWAP_PAGE_ID

NOW = datetime.fromisoformat("2026-11-24T16:00:00+02:00")
SECRET = "EAAG_FAKE_TEST_TOKEN"


class Reply:
    status = 200
    def __init__(self, payload):
        self.content = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, n):
        return self.content[:n]


class Opener:
    def __init__(self, feed=None, err=None):
        self.feed = feed if feed is not None else {"data": []}
        self.err = err
        self.requests = []
    def open(self, request: Request, timeout):
        self.requests.append((request, timeout))
        if self.err:
            raise self.err
        if request.full_url == GRAPH_ME_URL:
            response = {"id": COINOSWAP_PAGE_ID, "name": "Coinoswap"}
        else:
            response = self.feed
        return Reply(json.dumps(response).encode())


class PageReadbackTests(unittest.TestCase):
    def test_no_token_causes_zero_requests(self):
        o = Opener()
        report = audit_page_published_posts(environ={}, opener=o, at_sast=NOW)
        self.assertEqual(report.status, "NOT_CONFIGURED")
        self.assertEqual(o.requests, [])

    def test_two_fixed_get_calls_and_no_secret_in_output(self):
        o = Opener({"data": [{"id": COINOSWAP_PAGE_ID + "_123",
                             "message": "BTC ETH XMR daily rates",
                             "created_time": "2026-11-24T13:00:00+00:00"}]})
        report = audit_page_published_posts(
            environ={TOKEN_ENV: SECRET}, opener=o, at_sast=NOW)
        self.assertEqual(report.status, "POSSIBLE_DUPLICATE")
        self.assertEqual(len(o.requests), 2)
        self.assertEqual([r.full_url for r, _ in o.requests], [GRAPH_ME_URL, PAGE_POSTS_URL])
        for request, timeout in o.requests:
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(timeout, 8)
            self.assertEqual(request.get_header("Authorization"), "Bearer " + SECRET)
            self.assertNotIn(SECRET, request.full_url)
        self.assertNotIn(SECRET, repr(report))
        self.assertEqual(report.published_posts_created, 0)

    def test_empty_feed_is_not_clear_to_publish(self):
        report = audit_page_published_posts(
            environ={TOKEN_ENV: SECRET}, opener=Opener(), at_sast=NOW)
        self.assertEqual(report.status, "UNVERIFIED")
        self.assertEqual(report.published_posts_created, 0)

    def test_pagination_cannot_prove_clear(self):
        report = audit_page_published_posts(
            environ={TOKEN_ENV: SECRET},
            opener=Opener({"data": [], "paging": {"next": "https://graph.facebook.com/next"}}),
            at_sast=NOW)
        self.assertEqual(report.status, "UNVERIFIED")
        self.assertFalse(report.all_pages_inspected)

    def test_only_allowlisted_get_urls(self):
        with self.assertRaises(ValueError):
            _get_json(Opener(), "https://attacker.example/", SECRET, 64)

    def test_network_failure_no_retry_or_leak(self):
        o = Opener(err=URLError(SECRET))
        result = audit_page_published_posts(
            environ={TOKEN_ENV: SECRET}, opener=o, at_sast=NOW)
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(len(o.requests), 1)
        self.assertNotIn(SECRET, repr(result))

    def test_http_error_no_retry_and_redacted(self):
        for status, expected in [(302, "REDIRECT_BLOCKED"), (403, "AUTH_REJECTED"),
                                 (429, "RATE_LIMITED"), (503, "API_ERROR")]:
            with self.subTest(code=status):
                e = HTTPError(GRAPH_ME_URL, status, SECRET, {}, io.BytesIO(b"private"))
                o = Opener(err=e)
                result = audit_page_published_posts(
                    environ={TOKEN_ENV: SECRET}, opener=o, at_sast=NOW)
                self.assertEqual(result.status, expected)
                self.assertEqual(len(o.requests), 1)
                self.assertNotIn(SECRET, repr(result))

    def test_response_cap_rejects_oversized_body(self):
        class HugeOpener:
            def open(self, request, timeout):
                if request.full_url == GRAPH_ME_URL:
                    return Reply(json.dumps({
                        "id": COINOSWAP_PAGE_ID, "name": "Coinoswap"
                    }).encode())
                return Reply(b" " * (MAX_PAGE_RESPONSE + 1))
        report = audit_page_published_posts(environ={TOKEN_ENV: SECRET},
            opener=HugeOpener(), at_sast=NOW)
        self.assertEqual(report.status, "UNVERIFIED")

    def test_explicit_command_required(self):
        with patch("facebook_page_readback.audit_page_published_posts") as audit:
            with patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as e:
                    main([])
            self.assertEqual(e.exception.code, 2)
            audit.assert_not_called()

    def test_cli_missing_token_never_publishes(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["--check"])
        self.assertEqual(code, 2)
        self.assertIn("NOT_CONFIGURED", out.getvalue())
        self.assertNotIn(SECRET, out.getvalue())


if __name__ == "__main__":
    unittest.main()
