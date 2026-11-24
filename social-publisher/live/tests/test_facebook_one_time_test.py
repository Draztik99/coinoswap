"""Mock-only tests: no Facebook or GitHub network requests."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from facebook_one_time_test import one_time_test, APPROVAL, FEED_URL, MESSAGE, GRAPH_ME_URL, PAGE_POSTS_URL
from tag_ledger import TEST_TAG, ReservationBlocked

SECRET = "EAAG_FAKE_DO_NOT_USE"


class Reply:
    status = 200
    def __init__(self, data): self.raw = json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, n): return self.raw[:n]


class Transport:
    def __init__(self, duplicate=False, error_on_post=False, wrong_owner=False):
        self.calls=[]
        self.duplicate=duplicate
        self.error_on_post=error_on_post
        self.wrong_owner=wrong_owner
    def open(self, req, timeout):
        self.calls.append(req)
        if req.full_url == GRAPH_ME_URL:
            return Reply({"id":"108130358772133", "name":"Coinoswap"})
        if req.full_url == PAGE_POSTS_URL:
            return Reply({"data":[{"id":"108130358772133_55", "message": MESSAGE}] if self.duplicate else []})
        if req.get_method()=="POST":
            if self.error_on_post: raise TimeoutError("private Meta exception")
            return Reply({"id":"108130358772133_456"})
        return Reply({
            "id":"108130358772133_456", "message":MESSAGE,
            "from":{"id":"999" if self.wrong_owner else "108130358772133"},
            "permalink_url":"https://www.facebook.com/Coinoswap/posts/456"})


class SingleLiveTestSafety(unittest.TestCase):
    def run_test(self, transport, **overrides):
        kwargs = dict(token=SECRET, approval=APPROVAL, enabled="true",
                      repository=Path("/tmp/not_used"), opener=transport)
        kwargs.update(overrides)
        with patch("facebook_one_time_test.TagReservation") as ledger:
            ledger.return_value.reserve_one_time_test.return_value=TEST_TAG
            out=one_time_test(**kwargs)
        return out,transport.calls,ledger

    def test_no_approval_or_enable_means_zero_api_calls(self):
        for kwargs in ({"approval":""},{"enabled":""},{"token":"bad token"}):
            transport=Transport()
            result,calls,ledger=self.run_test(transport,**kwargs)
            self.assertEqual(result.status,"BLOCKED")
            self.assertEqual(calls,[])
            ledger.assert_not_called()

    def test_real_post_attempt_once_after_reservation(self):
        result,calls,ledger=self.run_test(Transport())
        self.assertEqual(result.status,"VERIFIED")
        self.assertEqual(result.provider_post_id,"108130358772133_456")
        self.assertEqual(sum(req.get_method()=="POST" for req in calls),1)
        self.assertEqual([req.full_url for req in calls if req.get_method()=="POST"],[FEED_URL])
        ledger.return_value.reserve_one_time_test.assert_called_once()
        self.assertNotIn(SECRET,repr(result))

    def test_duplicate_message_blocks_before_reservation(self):
        result,calls,ledger=self.run_test(Transport(duplicate=True))
        self.assertEqual(result.status,"BLOCKED")
        self.assertFalse(any(req.get_method()=="POST" for req in calls))
        ledger.assert_not_called()

    def test_post_timeout_does_not_retry(self):
        result,calls,ledger=self.run_test(Transport(error_on_post=True))
        self.assertEqual(result.status,"UNKNOWN")
        self.assertEqual(sum(req.get_method()=="POST" for req in calls),1)
        self.assertNotIn(SECRET,repr(result))

    def test_wrong_owner_never_reports_verified(self):
        result,calls,_=self.run_test(Transport(wrong_owner=True))
        self.assertEqual(result.status,"UNKNOWN")

    def test_existing_tag_blocks_post(self):
        transport=Transport()
        with patch("facebook_one_time_test.TagReservation") as ledger:
            ledger.return_value.reserve_one_time_test.side_effect=ReservationBlocked("exists")
            out=one_time_test(token=SECRET,approval=APPROVAL,enabled="true",
                              repository=Path("/tmp/not_used"),opener=transport)
        self.assertEqual(out.status,"BLOCKED")
        self.assertFalse(any(r.get_method()=="POST" for r in transport.calls))


if __name__=="__main__":
    unittest.main()
