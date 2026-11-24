"""Mocked Page transport; no GitHub tag pushes or real Facebook POSTs."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_reader import ValidatedAsset
from facebook_once import publish_once, APPROVAL_PHRASE, PAGE_POST_ENDPOINT, DeliveryResult
from facebook_health import GRAPH_ME_URL
from facebook_page_readback import PAGE_POSTS_URL
from tag_ledger import ReservationBlocked

SECRET = "EAAG_TEST_SECRET_DO_NOT_USE"
DAY = "2026-11-25"
COMMIT = "a" * 40
ENV = {"COINOSWAP_FB_LIVE_ENABLED": "true", "COINOSWAP_METRICOOL_FB_DISABLED": "confirmed"}
NOW = datetime.fromisoformat("2026-11-25T12:30:10+02:00")


def asset():
    return ValidatedAsset(
        date_sast=DAY, target_sast="2026-11-25T12:30:00+02:00",
        image_sha256="a" * 64, caption="CoinoSwap BTC ETH XMR daily rates",
        display_prices={"BTC":"$1", "ETH":"$2", "XMR":"$3"},
    )


class Reply:
    status = 200
    def __init__(self, obj):
        self.content = json.dumps(obj).encode()
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, n):
        return self.content[:n]


class FakeMeta:
    def __init__(self, *, duplicate=False, bad_readback=False, post_error=False):
        self.requests = []
        self.duplicate = duplicate
        self.bad_readback = bad_readback
        self.post_error = post_error

    def open(self, req, timeout):
        self.requests.append((req, timeout))
        if req.get_method() == "POST":
            if self.post_error:
                raise TimeoutError("private provider details")
            return Reply({"id":"123456"})
        if req.full_url == GRAPH_ME_URL:
            return Reply({"id":"108130358772133","name":"Coinoswap"})
        if req.full_url == PAGE_POSTS_URL:
            if self.duplicate:
                return Reply({"data":[{
                    "id":"108130358772133_789","message":"BTC ETH XMR",
                    "created_time":"2026-11-25T10:30:00+00:00"}]})
            return Reply({"data":[]})
        if self.bad_readback:
            return Reply({"id":"123456","page_story_id":"999_789","from":{"id":"999"},
                          "link":"https://www.facebook.com/elsewhere"})
        return Reply({"id":"123456","page_story_id":"108130358772133_789",
                      "from":{"id":"108130358772133"},
                      "link":"https://www.facebook.com/coinoswap/posts/789"})


class FacebookOnceTests(unittest.TestCase):
    def send(self, meta, ledger, **override):
        kwargs = dict(pinned_commit=COMMIT, token=SECRET, environ=ENV,
                      approval_phrase=APPROVAL_PHRASE, reservation=ledger,
                      opener=meta, clock=lambda: NOW)
        kwargs.update(override)
        return publish_once(asset(), **kwargs)

    def test_missing_approval_or_cutover_never_makes_requests(self):
        for value in ("", "yes", "I_APPROVE"):
            meta=FakeMeta(); ledger=Mock()
            r=self.send(meta, ledger, approval_phrase=value)
            self.assertEqual(r.status,"BLOCKED")
            self.assertEqual(meta.requests,[])
            ledger.reserve.assert_not_called()
        for config in ({}, {"COINOSWAP_FB_LIVE_ENABLED":"true"}):
            meta=FakeMeta(); ledger=Mock()
            r=self.send(meta, ledger, environ=config)
            self.assertEqual(r.status,"BLOCKED")
            self.assertEqual(meta.requests,[])
            ledger.reserve.assert_not_called()

    def test_stale_asset_blocks_before_meta_call(self):
        meta=FakeMeta();ledger=Mock()
        r=self.send(meta,ledger,clock=lambda:datetime.fromisoformat("2026-11-25T12:32:00+02:00"))
        self.assertEqual(r.status,"BLOCKED")
        self.assertEqual(meta.requests,[])
        ledger.reserve.assert_not_called()

    def test_possible_duplicate_blocks_without_reservation(self):
        meta=FakeMeta(duplicate=True); ledger=Mock()
        result=self.send(meta,ledger)
        self.assertEqual(result.status,"BLOCKED")
        self.assertFalse(any(req.get_method()=="POST" for req,_ in meta.requests))
        ledger.reserve.assert_not_called()

    def test_reservation_conflict_never_posts(self):
        meta=FakeMeta(); ledger=Mock()
        ledger.reserve.side_effect=ReservationBlocked("exists")
        r=self.send(meta,ledger)
        self.assertEqual(r.status,"BLOCKED")
        self.assertFalse(any(req.get_method()=="POST" for req,_ in meta.requests))

    def test_exactly_one_post_after_unique_reservation(self):
        meta=FakeMeta(); ledger=Mock()
        ledger.reserve.return_value="coinoswap-facebook-daily-rates-"+DAY
        r=self.send(meta,ledger)
        self.assertEqual(r.status,"PUBLISHED")
        self.assertEqual(r.provider_post_id,"108130358772133_789")
        self.assertEqual(r.public_url,"https://www.facebook.com/coinoswap/posts/789")
        post=[req for req,_ in meta.requests if req.get_method()=="POST"]
        self.assertEqual(len(post),1)
        self.assertEqual(post[0].full_url,PAGE_POST_ENDPOINT)
        self.assertNotIn(SECRET,post[0].full_url)
        self.assertEqual(post[0].get_header("Authorization"),"Bearer "+SECRET)
        self.assertNotIn(SECRET,repr(r))
        ledger.reserve.assert_called_once_with(DAY)

    def test_post_timeout_leaves_irreversible_reservation(self):
        meta=FakeMeta(post_error=True); ledger=Mock()
        ledger.reserve.return_value="coinoswap-facebook-daily-rates-"+DAY
        r=self.send(meta,ledger)
        self.assertEqual(r.status,"UNKNOWN")
        self.assertEqual(len([req for req,_ in meta.requests if req.get_method()=="POST"]),1)
        self.assertIn("manual reconciliation",r.reason)
        self.assertNotIn(SECRET,repr(r))

    def test_unverified_page_story_is_unknown_not_published(self):
        meta=FakeMeta(bad_readback=True); ledger=Mock()
        ledger.reserve.return_value="coinoswap-facebook-daily-rates-"+DAY
        r=self.send(meta,ledger)
        self.assertEqual(r.status,"UNKNOWN")
        self.assertIsNone(r.provider_post_id)


    def test_reservation_does_not_authorize_late_or_invalid_send(self):
        meta=FakeMeta(); ledger=Mock()
        ledger.reserve.return_value="coinoswap-facebook-daily-rates-"+DAY
        moments=iter([NOW, NOW, datetime.fromisoformat("2026-11-25T12:31:05+02:00")])
        result=self.send(meta,ledger,clock=lambda:next(moments))
        self.assertEqual(result.status,"RESERVED_NO_POST")
        self.assertEqual(len([req for req,_ in meta.requests if req.get_method()=="POST"]),0)
        ledger.reserve.assert_called_once_with(DAY)

    def test_unverified_reservation_tag_cannot_publish(self):
        meta=FakeMeta(); ledger=Mock()
        ledger.reserve.return_value=None
        result=self.send(meta,ledger)
        self.assertEqual(result.status,"BLOCKED")
        self.assertFalse(any(req.get_method()=="POST" for req,_ in meta.requests))

    def test_invalid_token_never_reserves(self):
        meta=FakeMeta(); ledger=Mock()
        r=self.send(meta,ledger,token="s p a c e")
        self.assertEqual(r.status,"BLOCKED")
        ledger.reserve.assert_not_called()
        self.assertEqual(meta.requests,[])


if __name__=="__main__":
    unittest.main()
