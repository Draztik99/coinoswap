"""Offline reservation tests; never pushes to a real repository."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tag_ledger import TagReservation, ReservationBlocked


class GitTagReservationTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.path = Path(self.t.name)

    def test_reservation_checks_remote_before_push(self):
        calls=[]
        def run(cmd, **kwargs):
            calls.append(cmd)
            if "ls-remote" in cmd: return CompletedProcess(cmd,2,b"",b"")
            return CompletedProcess(cmd,0,b"",b"")
        with patch("tag_ledger.subprocess.run",side_effect=run):
            tag = TagReservation(self.path).reserve("2026-11-25",request_id="abcdef123456")
        self.assertEqual(tag,"coinoswap-facebook-daily-rates-2026-11-25")
        self.assertEqual(len(calls),3)
        self.assertIn("ls-remote",calls[0])
        self.assertIn("tag",calls[1])
        self.assertIn("push",calls[2])
        self.assertNotIn("--force",str(calls))

    def test_existing_remote_tag_blocks_before_push(self):
        calls=[]
        def run(cmd, **kwargs):
            calls.append(cmd)
            return CompletedProcess(cmd,0,b"existing",b"")
        with patch("tag_ledger.subprocess.run",side_effect=run):
            with self.assertRaisesRegex(ReservationBlocked,"already reserved"):
                TagReservation(self.path).reserve("2026-11-25")
        self.assertEqual(len(calls),1)

    def test_unknown_lookup_fails_closed(self):
        with patch("tag_ledger.subprocess.run",return_value=CompletedProcess([],128,b"",b"SECRET")):
            with self.assertRaisesRegex(ReservationBlocked,"unavailable") as caught:
                TagReservation(self.path).reserve("2026-11-25")
        self.assertNotIn("SECRET",str(caught.exception))

    def test_failed_push_is_never_success(self):
        calls=[]
        def run(cmd, **kwargs):
            calls.append(cmd)
            return CompletedProcess(cmd,2 if "ls-remote" in cmd else
                                    1 if "push" in cmd else 0,b"",b"auth secret")
        with patch("tag_ledger.subprocess.run",side_effect=run):
            with self.assertRaisesRegex(ReservationBlocked,"push failed") as caught:
                TagReservation(self.path).reserve("2026-11-25",request_id="abcdef123456")
        self.assertNotIn("auth secret",str(caught.exception))
        self.assertEqual(len(calls),3)

    def test_invalid_date_or_nonce_fails_before_git(self):
        with patch("tag_ledger.subprocess.run") as run:
            for date in ("yesterday","2026-13-25","2026-11-1"):
                with self.assertRaises(ReservationBlocked):
                    TagReservation(self.path).reserve(date)
            with self.assertRaises(ReservationBlocked):
                TagReservation(self.path).reserve("2026-11-25",request_id="bad")
            run.assert_not_called()


if __name__=="__main__":
    unittest.main()
