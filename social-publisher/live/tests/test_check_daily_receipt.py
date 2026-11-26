"""Read-only receipt watchdog regression: regular and separate recovery media."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_daily_receipt import inspect, MissingVerifiedPublication

DAY="2026-11-25"
PAGE="108130358772133"
URL="https://www.facebook.com/photo.php?fbid=1138167732441661"
SHA="a"*40

class ReceiptWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"facebook-publications").mkdir()

    def pair(self, recovery=False):
        folder=self.root/"recovery" if recovery else self.root
        folder.mkdir(exist_ok=True)
        image=b"TEST_RECOVERY_BYTES" if recovery else b"TEST_ORIGINAL_BYTES"
        digest=hashlib.sha256(image).hexdigest()
        (folder/(DAY+".png")).write_bytes(image)
        (folder/(DAY+".json")).write_text(json.dumps({
            "date_sast":DAY,"status":"VALIDATED",
            "image":{"filename":DAY+".png","sha256":digest},
        }))
        return digest

    def receipt(self,digest,recovery=False):
        record={"date_sast":DAY,"platform":"facebook","status":"PUBLISHED",
            "verification":"META_PAGE_PHOTO_READBACK","page_id":PAGE,
            "reservation_tag":"coinoswap-facebook-daily-rates-"+DAY,
            "source_image_sha256":digest,
            "provider_post_id":PAGE+"_1138167745774993",
            "public_url":URL,"source_commit":SHA}
        if recovery:
            record["source_asset_path"]="docs/daily-rates/recovery/"+DAY+".json"
        (self.root/"facebook-publications"/(DAY+".json")).write_text(json.dumps(record))

    def test_normal_post_receipt_passes_without_recovery_field(self):
        digest=self.pair()
        self.receipt(digest)
        result=inspect(DAY,self.root)
        self.assertEqual(result["status"],"VERIFIED_PUBLICATION_RECEIPT")

    def test_valid_recovery_passes_using_distinct_immutable_source(self):
        self.pair()
        recovered=self.pair(recovery=True)
        self.receipt(recovered,recovery=True)
        result=inspect(DAY,self.root)
        self.assertEqual(result["status"],"VERIFIED_PUBLICATION_RECEIPT")
        self.assertEqual(result["provider_post_id"],PAGE+"_1138167745774993")

    def test_recovery_source_mismatch_never_confirms_post(self):
        original=self.pair()
        different=self.pair(recovery=True)
        self.assertNotEqual(original,different)
        self.receipt(original,recovery=True)
        with self.assertRaisesRegex(MissingVerifiedPublication,"FACEBOOK_RECEIPT_MISMATCH"):
            inspect(DAY,self.root)

    def test_missing_recovery_source_is_rejected(self):
        self.pair()
        self.receipt(hashlib.sha256(b"missing").hexdigest(),recovery=True)
        with self.assertRaisesRegex(MissingVerifiedPublication,"SOURCE_MISSING"):
            inspect(DAY,self.root)

    def test_receipt_never_follows_arbitrary_asset_paths(self):
        self.pair()
        digest=self.pair(recovery=True)
        self.receipt(digest,recovery=True)
        path=self.root/"facebook-publications"/(DAY+".json")
        record=json.loads(path.read_text())
        for source in ("../../private.json","docs/daily-rates/recovery/2026-11-24.json",
                       "https://example.com/a.json"):
            record["source_asset_path"]=source
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(MissingVerifiedPublication,"SOURCE_PATH_INVALID"):
                inspect(DAY,self.root)

if __name__=="__main__":
    unittest.main()
