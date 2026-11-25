"""Mock-only tests for the Facebook GET-only Page feed diagnostic."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from facebook_page_preflight import check_page_feed, TOKEN_ENV
from facebook_reconciliation import PAGE_SIZE

NOW = datetime.fromisoformat("2026-11-25T14:20:00+02:00")
SECRET = "EAAG_FAKE_PREVIEW_TOKEN"


class FakeResponse:
    status = 200

    def __init__(self, value):
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, length):
        return self.body[:length]


class FakeGraph:
    def __init__(self, *, denied=False, malformed=False):
        self.requests = []
        self.denied = denied
        self.malformed = malformed

    def open(self, request, timeout):
        self.requests.append(request)
        if request.get_method() != "GET":
            raise AssertionError("POST forbidden in diagnostic")
        if self.denied:
            raise HTTPError(request.full_url, 403, "PRIVATE", {}, None)
        return FakeResponse({} if self.malformed else {"data": []})


class ReadOnlyPreflightTests(unittest.TestCase):
    def test_successful_feed_probe_uses_only_get_and_hides_credentials(self):
        graph = FakeGraph()
        result = check_page_feed(environ={TOKEN_ENV: SECRET}, opener=graph, now=NOW)
        self.assertEqual(result.status, "PAGE_FEED_ACCESSIBLE")
        self.assertTrue(result.all_pages_inspected)
        self.assertEqual(len(graph.requests), 1)
        self.assertEqual(graph.requests[0].get_method(), "GET")
        self.assertNotIn(SECRET, graph.requests[0].full_url)
        self.assertIn("since=", graph.requests[0].full_url)
        self.assertNotIn(SECRET,repr(result))

    def test_denied_feed_is_numeric_only_and_never_posts(self):
        graph = FakeGraph(denied=True)
        result = check_page_feed(environ={TOKEN_ENV: SECRET}, opener=graph, now=NOW)
        self.assertEqual(result.status, "PAGE_FEED_HTTP_REJECTED")
        self.assertEqual(result.http_status, 403)
        self.assertNotIn(SECRET,repr(result))
        self.assertEqual([r.get_method() for r in graph.requests], ["GET"])

    def test_invalid_token_or_clock_fails_before_request(self):
        graph = FakeGraph()
        result = check_page_feed(environ={TOKEN_ENV: ""}, opener=graph, now=NOW)
        self.assertEqual(result.status,"TOKEN_NOT_CONFIGURED")
        self.assertEqual(graph.requests, [])
        result = check_page_feed(environ={TOKEN_ENV: SECRET}, opener=graph,
                                 now=datetime(2026,11,25,14,20))
        self.assertEqual(result.status,"INVALID_CLOCK")
        self.assertEqual(graph.requests, [])

    def test_malformed_feed_is_not_accepted(self):
        graph=FakeGraph(malformed=True)
        result=check_page_feed(environ={TOKEN_ENV:SECRET},opener=graph,now=NOW)
        self.assertEqual(result.status,"PAGE_FEED_INCOMPLETE")
        self.assertEqual([r.get_method() for r in graph.requests],["GET"])


if __name__=="__main__":
    unittest.main()
