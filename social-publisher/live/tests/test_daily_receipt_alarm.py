"""Tests for daily verified-Facebook-post watchdog (no API calls)."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_daily_receipt import MissingVerifiedPublication, inspect

DAY="2026-11-25"
PAGE="108130358772133"
PNG=b"offline-test-bytes"

class DailyReceiptAlarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"facebook-publications").mkdir()
        self.sha=hashlib.sha256(PNG).hexdigest()
        self.source={"status":"VALIDATED","date_sast":DAY,
                     "image":{"filename":DAY+".png","sha256":self.sha}}
        self.receipt={"date_sast":DAY,"platform":"facebook","status":"PUBLISHED",
                      "verification":"META_PAGE_PHOTO_READBACK","page_id":PAGE,
                      "reservation_tag":"coinoswap-facebook-daily-rates-"+DAY,
                      "source_image_sha256":self.sha,
                      "provider_post_id":PAGE+"_456",
                      "public_url":"https://www.facebook.com/coinoswap/posts/456",
                      "source_commit":"a"*40}
    def write(self):
        (self.root/(DAY+".png")).write_bytes(PNG)
        (self.root/(DAY+".json")).write_text(json.dumps(self.source))
        (self.root/"facebook-publications"/(DAY+".json")).write_text(json.dumps(self.receipt))
    def test_source_missing_blocks(self):
        with self.assertRaisesRegex(MissingVerifiedPublication,"SOURCE_MISSING"):
            inspect(DAY,self.root)
    def test_verified_receipt_passes(self):
        self.write()
        out=inspect(DAY,self.root)
        self.assertEqual(out["status"],"VERIFIED_PUBLICATION_RECEIPT")
        self.assertEqual(out["provider_post_id"],PAGE+"_456")
    def test_receipt_missing_blocks(self):
        self.write()
        (self.root/"facebook-publications"/(DAY+".json")).unlink()
        with self.assertRaisesRegex(MissingVerifiedPublication,"FACEBOOK_RECEIPT_MISSING"):
            inspect(DAY,self.root)
    def test_unverified_or_wrong_platform_blocks(self):
        for update in ({"status":"PENDING"},{"platform":"instagram"},
                       {"verification":"UNKNOWN"},{"page_id":"999"},
                       {"source_image_sha256":"b"*64},
                       {"reservation_tag":"wrong-tag"}):
            with self.subTest(update=update):
                self.write()
                self.receipt.update(update)
                (self.root/"facebook-publications"/(DAY+".json")).write_text(json.dumps(self.receipt))
                with self.assertRaises(MissingVerifiedPublication):
                    inspect(DAY,self.root)
                self.receipt={"date_sast":DAY,"platform":"facebook","status":"PUBLISHED",
                              "verification":"META_PAGE_PHOTO_READBACK","page_id":PAGE,
                              "reservation_tag":"coinoswap-facebook-daily-rates-"+DAY,
                              "source_image_sha256":self.sha,"provider_post_id":PAGE+"_456",
                              "public_url":"https://www.facebook.com/coinoswap/posts/456",
                              "source_commit":"a"*40}
    def test_wrong_domain_and_post_id_blocks(self):
        self.write()
        for changed in ({"public_url":"https://evil.example/posts/456"},
                        {"provider_post_id":"999_456"},
                        {"source_commit":"not-sha"}):
            with self.subTest(changed=changed):
                modified={**self.receipt,**changed}
                (self.root/"facebook-publications"/(DAY+".json")).write_text(json.dumps(modified))
                with self.assertRaises(MissingVerifiedPublication):
                    inspect(DAY,self.root)
    def test_corrupt_image_checksum_blocks(self):
        self.write()
        (self.root/(DAY+".png")).write_bytes(b"changed")
        with self.assertRaisesRegex(MissingVerifiedPublication,"SOURCE_INTEGRITY_FAILED"):
            inspect(DAY,self.root)
    def test_noncanonical_day_rejected(self):
        with self.assertRaises(MissingVerifiedPublication):
            inspect("2026-11-5",self.root)


if __name__ == "__main__":
    unittest.main()
