"""Metricool import tests: only verified provider fields, no publication."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from instagram_import import convert,save
from model import AnalyticsError

NOW=datetime.fromisoformat("2026-11-24T19:48:08+02:00")
ROW=["20261122121000","Your 22 November crypto price check 📊\n$BTC, $ETH and $XMR",
     "18123539791745350","https://www.instagram.com/p/DgCxZXKDTe3/",
     "0","0.0","0","0","3","0","0","4"]

class ImporterTests(unittest.TestCase):
    def test_official_data_imported(self):
        r=convert({"rows":[ROW]},collected_at=NOW)
        self.assertEqual(len(r["records"]),1)
        self.assertEqual(r["records"][0]["metrics"]["reach"],3)
        self.assertEqual(r["records"][0]["metrics"]["interactions"],0)

    def test_non_campaign_not_saved(self):
        row=list(ROW)
        row[1]="A different unrelated post"
        r=convert({"rows":[row]},collected_at=NOW)
        self.assertEqual(r["records"],[])

    def test_invalid_provider_response_fails(self):
        for p in ({}, {"rows":"invalid"}, {"rows":[ROW,ROW]}):
            with self.assertRaises(AnalyticsError):
                convert(p,collected_at=NOW)

    def test_save_once_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"snapshot.json"
            data=convert({"rows":[ROW]},collected_at=NOW)
            save(data,path)
            self.assertEqual(json.loads(path.read_text())["brand_id"],"8283300")
            with self.assertRaises(AnalyticsError):
                save(data,path)

if __name__=="__main__":
    unittest.main()
