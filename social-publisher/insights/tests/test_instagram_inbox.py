"""Offline-only Metricool connector inbox bridge tests."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from instagram_inbox import process_inbox,validate_inbox
from model import IG_FIELDS,AnalyticsError

ROW=["20261122121000","Your 22 November crypto price check 📊 $BTC, $ETH and $XMR",
     "18123539791745350","https://www.instagram.com/p/DgCxZXKDTe3/",
     "0","0.0","0","0","3","0","0","4"]
SOURCE={"schema_version":1,"brand_id":"8283300","metric_field_ids":list(IG_FIELDS),
        "retrieved_at_sast":"2026-11-24T19:48:08+02:00","rows":[ROW]}


class MetricoolInboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.inbox=Path(self.temp.name)/"inbox"
        self.output=Path(self.temp.name)/"snapshots"
        self.inbox.mkdir()
    def write(self, content=None):
        (self.inbox/"2026-11-24.json").write_text(json.dumps(content if content is not None else SOURCE))

    def test_imports_verified_metricool_row_without_network(self):
        self.write()
        result=process_inbox(inbox=self.inbox,output=self.output)
        self.assertEqual(result["imported"],1)
        self.assertEqual(result["records_imported"],1)
        data=json.loads((self.output/"2026-11-24.json").read_text())
        self.assertEqual(data["records"][0]["metrics"]["reach"],3)
        self.assertEqual(data["records"][0]["metrics"]["interactions"],0)

    def test_idempotent_never_overwrites(self):
        self.write()
        process_inbox(inbox=self.inbox,output=self.output)
        result=process_inbox(inbox=self.inbox,output=self.output)
        self.assertEqual(result["imported"],0)
        self.assertEqual(result["skipped_existing"],1)
        self.assertEqual(result["records_imported"],0)

    def test_invalid_brand_and_layout_rejected(self):
        for change in ({"brand_id":"123"},{"metric_field_ids":["BAD"]},
                       {"retrieved_at_sast":"2026-11-23T19:48:08+02:00"}):
            with self.subTest(change=change):
                self.write({**SOURCE,**change})
                with self.assertRaises(AnalyticsError):
                    process_inbox(inbox=self.inbox,output=self.output)
                self.assertFalse(list(self.output.glob("*.json")))

    def test_absent_inbox_safe_noop(self):
        self.assertEqual(process_inbox(inbox=self.inbox/"missing",output=self.output)["imported"],0)
        self.assertEqual(process_inbox(inbox=self.inbox/"missing",output=self.output)["records_imported"],0)

    def test_no_social_transport(self):
        code=(Path(__file__).resolve().parents[1]/"instagram_inbox.py").read_text()
        self.assertNotIn("requests.post(",code)
        self.assertNotIn("urlopen(",code)
        self.assertNotIn("access_token",code)

if __name__=="__main__":
    unittest.main()
