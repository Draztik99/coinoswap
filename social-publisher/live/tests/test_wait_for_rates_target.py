"""No-network tests for fresh-price manual target gate."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wait_for_rates_target import seconds_until_target, WaitBlocked, SAST

NOW = datetime.fromisoformat("2026-11-24T19:05:00+02:00")
def manifest(target="2026-11-24T19:07:00+02:00", checked="2026-11-24T19:04:20+02:00"):
    return {"status":"VALIDATED","date_sast":"2026-11-24",
            "target_sast":target,"checked_at_sast":checked}

class WaitTargetTests(unittest.TestCase):
    def test_newly_validated_image_waits_until_target(self):
        self.assertEqual(seconds_until_target(manifest(),now=NOW),120)
    def test_at_target_may_proceed(self):
        at = datetime.fromisoformat("2026-11-24T19:07:00+02:00")
        self.assertEqual(seconds_until_target(manifest(),now=at),0)
    def test_25s_grace_but_no_extended_stale_publication(self):
        at = datetime.fromisoformat("2026-11-24T19:07:25+02:00")
        self.assertEqual(seconds_until_target(manifest(),now=at),0)
        at += timedelta(seconds=1)
        with self.assertRaises(WaitBlocked):
            seconds_until_target(manifest(),now=at)
    def test_too_far_ahead_is_blocked(self):
        with self.assertRaises(WaitBlocked):
            seconds_until_target(manifest(target="2026-11-24T19:20:00+02:00"),now=NOW)
    def test_bad_dates_and_unvalidated(self):
        for item in (
            {"status":"NOT_VALIDATED",**{k:v for k,v in manifest().items() if k!="status"}},
            {**manifest(),"date_sast":"2026-11-23"},
            manifest(target="2026-11-25T00:00:00+02:00"),
            manifest(checked="2026-11-24T19:09:00+02:00"),
            {},
        ):
            with self.subTest(item=item):
                with self.assertRaises(WaitBlocked):
                    seconds_until_target(item,now=NOW)
    def test_naive_clock_is_rejected(self):
        with self.assertRaises(WaitBlocked):
            seconds_until_target(manifest(),now=datetime(2026,11,24,19,5))
    def test_no_external_network_or_post_path(self):
        src=(Path(__file__).resolve().parents[1]/"wait_for_rates_target.py").read_text()
        self.assertNotIn("urlopen(",src)
        self.assertNotIn("requests.post(",src)
        self.assertNotIn("access_token",src.lower())

if __name__=="__main__":
    unittest.main()
