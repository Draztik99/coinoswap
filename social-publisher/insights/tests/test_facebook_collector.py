"""Mock-only integration tests for Meta read-only analytics collection."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from facebook_collector import collect, CollectorUnavailable, PAGE_ID, GRAPH_ME_URL

NOW=datetime.fromisoformat("2026-11-25T18:30:00+02:00")
PID=PAGE_ID+"_1137307232527711"
SECRET="EAAG_FAKE_ONLY"
RECEIPT={"platform":"facebook","status":"PUBLISHED","verification":"META_PAGE_PHOTO_READBACK",
         "date_sast":"2026-11-24","page_id":PAGE_ID,"provider_post_id":PID,
         "published_at_sast":"2026-11-24T19:19:05+02:00",
         "public_url":"https://www.facebook.com/photo.php?fbid=1137307215861046"}


class Response:
    status=200
    def __init__(self, x):self.bytes=json.dumps(x).encode()
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read(self,n):return self.bytes[:n]


class FakeGraph:
    def __init__(self, *, deny_insights=False, wrong_owner=False, reject_post=False):
        self.requests=[]
        self.deny_insights=deny_insights
        self.wrong_owner=wrong_owner
        self.reject_post=reject_post
    def open(self, req, timeout):
        self.requests.append(req)
        if req.get_method()!="GET":raise AssertionError("No POST permitted")
        if req.full_url==GRAPH_ME_URL:return Response({"id":PAGE_ID,"name":"Coinoswap"})
        if "/insights?" in req.full_url:
            if self.deny_insights:raise HTTPError(req.full_url,403,"no permission",{},None)
            return Response({"data":[{"name":"post_media_view","values":[{"value":37}]}]})
        if self.reject_post:raise HTTPError(req.full_url,403,"invalid",{},None)
        return Response({"id":PID,"from":{"id":"999" if self.wrong_owner else PAGE_ID},
                         "reactions":{"summary":{"total_count":6}},
                         "comments":{"summary":{"total_count":0}},
                         "shares":{"count":2}})


class FacebookCollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"receipts"
        self.out=Path(self.tmp.name)/"snapshots"
        self.root.mkdir()
        (self.root/"2026-11-24.json").write_text(json.dumps(RECEIPT))

    def test_first_snapshot_uses_real_graph_gets_and_is_immutable(self):
        mock=FakeGraph()
        r=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=mock)
        self.assertEqual(r["snapshots_created"],1)
        saved=json.loads((self.out/"2026-11-24"/"2026-11-25.json").read_text())
        self.assertEqual(saved["metrics"]["views"],37)
        self.assertEqual(saved["metrics"]["comments"],0)
        self.assertEqual(saved["metrics"]["interactions"],8)
        self.assertIsNone(saved["metrics"]["reach"])
        self.assertTrue(all(x.get_method()=="GET" for x in mock.requests))
        self.assertNotIn(SECRET,json.dumps(saved))
        r2=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=mock)
        self.assertEqual(r2["snapshots_created"],0)

    def test_coverage_counts_distinguish_eligible_and_already_collected(self):
        graph=FakeGraph()
        first=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=graph)
        self.assertEqual(first["posts_eligible"],1)
        self.assertEqual(first["snapshots_created"],1)
        self.assertEqual(first["snapshots_already_present"],0)
        self.assertEqual(first["receipts_outside_collection_window"],0)
        self.assertEqual(first["collection_window_days"],32)
        calls=len(graph.requests)
        second=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=graph)
        self.assertEqual(second["posts_eligible"],1)
        self.assertEqual(second["snapshots_created"],0)
        self.assertEqual(second["snapshots_already_present"],1)
        # Repeated runs only check token identity; do not re-fetch same-day post metrics.
        self.assertEqual(len(graph.requests),calls+1)

    def test_old_receipts_are_excluded_and_counted_without_api_requests(self):
        dated="2026-10-01"
        old={**RECEIPT,"date_sast":dated}
        (self.root/"2026-11-24.json").unlink()
        (self.root/(dated+".json")).write_text(json.dumps(old))
        graph=FakeGraph()
        result=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=graph)
        self.assertEqual(result["posts_eligible"],0)
        self.assertEqual(result["snapshots_created"],0)
        self.assertEqual(result["receipts_outside_collection_window"],1)
        self.assertEqual(len(graph.requests),1)

    def test_denied_optional_insights_is_na_not_zero(self):
        x=collect(token=SECRET,now=NOW,root=self.root,output=self.out,
                  opener=FakeGraph(deny_insights=True))
        saved=json.loads((self.out/"2026-11-24"/"2026-11-25.json").read_text())
        self.assertIsNone(saved["metrics"]["views"])
        self.assertEqual(x["snapshots_created"],1)

    def test_wrong_page_or_unavailable_post_fails_without_snapshot(self):
        for kwargs in ({"wrong_owner":True},{"reject_post":True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(CollectorUnavailable):
                    collect(token=SECRET,now=NOW,root=self.root,output=self.out,
                            opener=FakeGraph(**kwargs))
                self.assertFalse(list(self.out.glob("**/*.json")))


    def test_photo_readback_fallback_preserves_unavailable_metrics(self):
        from urllib.parse import parse_qs, urlsplit
        PHOTO = "1137307215861046"
        class PhotoOnlyGraph(FakeGraph):
            def open(self, req, timeout):
                if req.full_url == GRAPH_ME_URL:
                    return super().open(req, timeout)
                self.requests.append(req)
                if req.get_method() != "GET":
                    raise AssertionError("No POST in analytics")
                if "/"+PID+"?" in req.full_url:
                    raise HTTPError(req.full_url, 400, "post not accessible", {}, None)
                if "/"+PHOTO+"/insights?" in req.full_url:
                    raise HTTPError(req.full_url, 403, "metric unsupported", {}, None)
                if "/"+PHOTO+"?" in req.full_url:
                    fields = parse_qs(urlsplit(req.full_url).query).get("fields", [""])[0]
                    if "page_story_id" in fields:
                        return Response({"id":PHOTO,"page_story_id":PID,
                            "from":{"id":PAGE_ID},
                            "link":"https://www.facebook.com/photo.php?fbid="+PHOTO})
                    raise HTTPError(req.full_url, 403, "counts unavailable", {}, None)
                raise AssertionError("unapproved GET")
        graph=PhotoOnlyGraph()
        result=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=graph)
        self.assertEqual(result["snapshots_created"],1)
        snapshot=json.loads((self.out/"2026-11-24"/"2026-11-25.json").read_text())
        self.assertEqual(snapshot["source"],"Meta Graph API v27.0 verified photo readback")
        self.assertIsNone(snapshot["metrics"]["comments"])
        self.assertIsNone(snapshot["metrics"]["views"])
        self.assertIsNone(snapshot["metrics"]["interactions"])
        self.assertTrue(all(r.get_method()=="GET" for r in graph.requests))

    def test_photo_readback_fallback_rejects_wrong_page_story(self):
        PHOTO="1137307215861046"
        class WrongStory(FakeGraph):
            def open(self,req,timeout):
                if req.full_url==GRAPH_ME_URL:
                    return super().open(req,timeout)
                if "/"+PID+"?" in req.full_url:
                    raise HTTPError(req.full_url,400,"post inaccessible",{},None)
                return Response({"id":PHOTO,"page_story_id":"999_11",
                                 "from":{"id":PAGE_ID},
                                 "link":"https://www.facebook.com/photo.php?fbid="+PHOTO})
        with self.assertRaises(CollectorUnavailable):
            collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=WrongStory())
        self.assertEqual(list(self.out.glob("**/*.json")),[])

    def test_bad_receipt_fails_closed(self):
        p=self.root/"2026-11-24.json"
        p.write_text(json.dumps({**RECEIPT,"page_id":"999"}))
        with self.assertRaises(CollectorUnavailable):
            collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=FakeGraph())

    def test_no_token_means_no_network(self):
        meta=FakeGraph()
        with self.assertRaises(CollectorUnavailable):
            collect(token="",now=NOW,root=self.root,output=self.out,opener=meta)
        self.assertEqual(meta.requests,[])

    def test_zero_receipts_is_reported_not_fabricated(self):
        (self.root/"2026-11-24.json").unlink()
        r=collect(token=SECRET,now=NOW,root=self.root,output=self.out,opener=FakeGraph())
        self.assertEqual(r["status"],"COLLECTED")
        self.assertEqual(r["snapshots_created"],0)


if __name__=="__main__":
    unittest.main()
