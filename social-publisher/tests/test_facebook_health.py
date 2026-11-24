"""Offline checks for the explicit GET-only Facebook credential diagnostic."""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from facebook_health import (
    COINOSWAP_PAGE_ID, GRAPH_ME_URL, TOKEN_ENV, MAX_RESPONSE_BYTES,
    _RejectRedirects, check_page_token, main,
)

SECRET = "EAAG_TEST_SECRET_NOT_REAL"


class FakeResponse:
    status = 200

    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount: int) -> bytes:
        return self.payload[:amount]


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def open(self, request: Request, timeout: int):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


class FacebookHealthTests(unittest.TestCase):
    def test_requires_secret_and_does_not_network_without_one(self):
        opener = FakeOpener()
        result = check_page_token(environ={}, opener=opener)
        self.assertEqual(result.status, "NOT_CONFIGURED")
        self.assertEqual(opener.calls, [])

    def test_invalid_token_rejected_without_network(self):
        for token in ("", " x ", "a" + chr(10) + "b", "a" + chr(13) + "b", "a b"):
            opener = FakeOpener()
            result = check_page_token(environ={TOKEN_ENV: token}, opener=opener)
            self.assertEqual(result.status, "INVALID_CONFIGURATION")
            self.assertEqual(opener.calls, [])

    def test_success_uses_exact_https_get_bearer_header_and_redacts(self):
        payload = ('{"id":"' + COINOSWAP_PAGE_ID + '","name":"Coinoswap"}').encode()
        opener = FakeOpener(FakeResponse(payload))
        result = check_page_token(environ={TOKEN_ENV: SECRET}, opener=opener)
        self.assertEqual(result.status, "VERIFIED_PAGE_IDENTITY")
        self.assertEqual(result.page_id, COINOSWAP_PAGE_ID)
        self.assertNotIn(SECRET, repr(result))
        self.assertEqual(len(opener.calls), 1)
        req, timeout = opener.calls[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, GRAPH_ME_URL)
        self.assertTrue(req.full_url.startswith("https://graph.facebook.com/v27.0/me?"))
        self.assertNotIn(SECRET, req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Bearer " + SECRET)
        self.assertEqual(timeout, 8)

    def test_wrong_page_or_meta_error_fails_closed(self):
        for payload in (b'{"id":"123","name":"Elsewhere"}',
                        b'{"error":{"message":"secret from Meta"}}',
                        b'{"name":"Coinoswap"}'):
            result = check_page_token(
                environ={TOKEN_ENV: SECRET}, opener=FakeOpener(FakeResponse(payload)))
            self.assertEqual(result.status, "IDENTITY_MISMATCH")
            self.assertNotIn(SECRET, str(result))
            self.assertNotIn("secret from Meta", str(result))

    def test_invalid_response_and_oversize_fail_closed(self):
        for payload in (b"<html>bad</html>", bytes([255]), b" " * (MAX_RESPONSE_BYTES + 1)):
            result = check_page_token(
                environ={TOKEN_ENV: SECRET}, opener=FakeOpener(FakeResponse(payload)))
            self.assertEqual(result.status, "UNEXPECTED_RESPONSE")

    def test_meta_errors_redacted_and_not_retried(self):
        cases = [(302, "REDIRECT_BLOCKED"), (400, "AUTH_REJECTED"),
                 (401, "AUTH_REJECTED"), (403, "AUTH_REJECTED"),
                 (429, "RATE_LIMITED"), (503, "API_ERROR")]
        for status, expected in cases:
            with self.subTest(status=status):
                error = HTTPError(GRAPH_ME_URL, status, SECRET, {}, io.BytesIO(b"private"))
                opener = FakeOpener(error=error)
                result = check_page_token(environ={TOKEN_ENV: SECRET}, opener=opener)
                self.assertEqual(result.status, expected)
                self.assertEqual(len(opener.calls), 1)
                self.assertNotIn(SECRET, repr(result))
                self.assertNotIn("private", repr(result))

    def test_safely_classifies_meta_token_expiry_codes(self):
        cases = [
            (401, 190, 463, "TOKEN_EXPIRED"),
            (401, 190, 467, "TOKEN_INVALID"),
            (401, 190, 460, "REAUTH_REQUIRED"),
            (403, 200, None, "AUTH_REJECTED"),
        ]
        for http_status, code, subcode, expected in cases:
            with self.subTest(expected=expected):
                payload = {
                    "error": {
                        "code": code,
                        "message": SECRET + " dangerous provider text",
                        "fbtrace_id": "PRIVATE_TRACE",
                    }
                }
                if subcode is not None:
                    payload["error"]["error_subcode"] = subcode
                error = HTTPError(
                    GRAPH_ME_URL, http_status, SECRET, {},
                    io.BytesIO(__import__("json").dumps(payload).encode())
                )
                result = check_page_token(
                    environ={TOKEN_ENV: SECRET}, opener=FakeOpener(error=error)
                )
                self.assertEqual(result.status, expected)
                self.assertEqual(result.http_status, http_status)
                self.assertEqual(result.meta_error_code, code)
                self.assertEqual(result.meta_error_subcode, subcode)
                self.assertNotIn(SECRET, repr(result))
                self.assertNotIn("PRIVATE_TRACE", repr(result))
                self.assertNotIn("dangerous provider text", repr(result))

    def test_invalid_meta_response_never_echoed(self):
        for response in (
            b"bad provider body " + SECRET.encode(),
            b" " * 4097,
            b'{"error":{"code":true,"error_subcode":"463"}}',
            b'{"error":{"code":190,"error_subcode":2147483648}}',
        ):
            error = HTTPError(GRAPH_ME_URL, 401, SECRET, {}, io.BytesIO(response))
            result = check_page_token(
                environ={TOKEN_ENV: SECRET}, opener=FakeOpener(error=error)
            )
            self.assertEqual(result.status, "AUTH_REJECTED")
            self.assertNotIn(SECRET, repr(result))
            self.assertNotIn("provider body", repr(result))


    def test_network_failure_redacted_and_not_retried(self):
        for error in (URLError(SECRET), TimeoutError(SECRET), ValueError(SECRET)):
            opener = FakeOpener(error=error)
            result = check_page_token(environ={TOKEN_ENV: SECRET}, opener=opener)
            self.assertEqual(result.status, "NETWORK_ERROR")
            self.assertEqual(len(opener.calls), 1)
            self.assertNotIn(SECRET, repr(result))

    def test_redirect_handler_denies_forwarding_bearer(self):
        req = Request(GRAPH_ME_URL, headers={"Authorization": "Bearer " + SECRET})
        self.assertIsNone(_RejectRedirects().redirect_request(
            req, None, 302, "Moved", {}, "https://untrusted.example/path"))

    def test_dry_default_cli_does_not_call_network(self):
        with patch("facebook_health.check_page_token") as check:
            with patch("sys.stderr", new=io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    main([])
            self.assertEqual(ctx.exception.code, 2)
            check.assert_not_called()

    def test_cli_without_secret_emits_no_token(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["--check"])
        self.assertEqual(code, 2)
        self.assertIn("NOT_CONFIGURED", out.getvalue())
        self.assertNotIn(SECRET, out.getvalue())


if __name__ == "__main__":
    unittest.main()
