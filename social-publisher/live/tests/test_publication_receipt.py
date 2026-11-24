"""Pure offline tests for durable, secret-free Facebook publication receipts."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publication_receipt import verified_receipt, write_receipt, ReceiptRejected, REASON

DAY = "2026-11-24"
SHA = "a" * 40
HASH = "b" * 64
RUN = "45446672302"
STAMP = datetime.fromisoformat("2026-11-24T19:19:05+02:00")


def result():
    return {"status":"PUBLISHED", "reason":REASON, "page_id":"108130358772133",
            "provider_post_id":"108130358772133_1137307232527711",
            "reservation_tag":"coinoswap-facebook-daily-rates-2026-11-24",
            "public_url":"https://www.facebook.com/photo.php?fbid=1137307215861046&set=a.537392199185887&type=3"}


def audit():
    return {"status":"VALIDATED", "approval_state":"NOT_PUBLISHED",
            "date_sast":DAY, "target_sast":"2026-11-24T19:19:00+02:00",
            "image":{"filename":DAY+".png","sha256":HASH}}


class PublicationReceiptsTests(unittest.TestCase):
    def verified(self, r=None, a=None, **kwargs):
        data={"source_commit":SHA,"github_run_id":RUN,"at_sast":STAMP}
        data.update(kwargs)
        return verified_receipt(result() if r is None else r, audit() if a is None else a, **data)

    def test_verified_result_is_separate_from_original_audit(self):
        original=audit()
        receipt=self.verified(a=original)
        self.assertEqual(receipt["status"],"PUBLISHED")
        self.assertEqual(original["approval_state"],"NOT_PUBLISHED")
        self.assertEqual(receipt["source_image_sha256"],HASH)
        self.assertEqual(receipt["github_run_id"],RUN)
        self.assertNotIn("access_token",json.dumps(receipt))
        self.assertNotIn("bearer",json.dumps(receipt).lower())

    def test_wrong_status_rejected(self):
        for state in ("BLOCKED","UNKNOWN","RESERVED_NO_POST","NOT_PUBLISHED"):
            with self.subTest(state=state):
                with self.assertRaises(ReceiptRejected):
                    self.verified(r={**result(),"status":state})

    def test_wrong_page_or_post_rejected(self):
        for update in ({"page_id":"999"},{"provider_post_id":"999_123"},
                       {"reservation_tag":"coinoswap-facebook-daily-rates-2026-11-23"},
                       {"reason":"POST returned but not read back"}):
            with self.subTest(update=update):
                with self.assertRaises(ReceiptRejected):
                    self.verified(r={**result(),**update})

    def test_wrong_source_identity_rejected(self):
        for update in ({"date_sast":"2026-11-23"}, {"status":"NOT_VALIDATED"},
                       {"image":{"filename":"yesterday.png","sha256":HASH}},
                       {"image":{"filename":DAY+".png","sha256":"not-a-hash"}}):
            with self.subTest(update=update):
                with self.assertRaises(ReceiptRejected):
                    self.verified(a={**audit(),**update})

    def test_only_public_facebook_permalink(self):
        for url in ("https://evil.example/photos/1", "http://www.facebook.com/photo.php",
                    "https://facebook.com.evil.example/post/1",
                    "https://www.facebook.com/photo.php?access_token=secret",
                    "https://www.facebook.com/photo.php#secret"):
            with self.subTest(url=url):
                with self.assertRaises(ReceiptRejected):
                    self.verified(r={**result(),"public_url":url})

    def test_time_must_match_sast_day_and_target(self):
        for timestamp in ("2026-11-25T00:01:00+02:00",
                          "2026-11-24T19:21:00+02:00",
                          "2026-11-24T19:18:00+02:00"):
            with self.subTest(time=timestamp):
                with self.assertRaises(ReceiptRejected):
                    self.verified(at_sast=datetime.fromisoformat(timestamp))

    def test_immutable_writes_and_no_duplicate_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            receipt=self.verified()
            path=write_receipt(receipt,root=root)
            saved=path.read_text()
            with self.assertRaisesRegex(ReceiptRejected,"already exists"):
                write_receipt(receipt,root=root)
            self.assertEqual(path.read_text(),saved)
            self.assertEqual(json.loads(saved)["status"],"PUBLISHED")

    def test_invalid_run_and_commit_rejected(self):
        for kw in ({"github_run_id":"fake"},{"source_commit":"short"}):
            with self.subTest(kw=kw):
                with self.assertRaises(ReceiptRejected):
                    self.verified(**kw)


if __name__ == "__main__":
    unittest.main()
