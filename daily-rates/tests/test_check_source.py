"""Read-only source generation audit tests with fake local PNG, no network."""
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_source import SourceMissing, audit_source

DAY = "2026-11-24"
PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1536, 1024) + b"test_data"

class ReadinessAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def valid_pair(self):
        (self.root / (DAY + ".png")).write_bytes(PNG)
        audit = {
            "status": "VALIDATED", "date_sast": DAY,
            "target_sast": "2026-11-24T14:30:00+02:00",
            "checked_at_sast": "2026-11-24T14:27:00+02:00",
            "image": {"filename": DAY + ".png", "sha256": hashlib.sha256(PNG).hexdigest(),
                      "width": 1536, "height": 1024},
        }
        (self.root / (DAY + ".json")).write_text(json.dumps(audit), encoding="utf-8")
        return audit

    def test_missing_source_never_counts_as_published(self):
        with self.assertRaisesRegex(SourceMissing, "absent"):
            audit_source(date_sast=DAY, directory=self.root)

    def test_valid_source_is_not_publication_receipt(self):
        self.valid_pair()
        result = audit_source(date_sast=DAY, directory=self.root)
        self.assertEqual(result["status"], "VALIDATED_SOURCE_PRESENT")
        self.assertEqual(result["social_posts_created"], 0)

    def test_wrong_day_source_fails(self):
        self.valid_pair()
        with self.assertRaises(SourceMissing):
            audit_source(date_sast="2026-11-25", directory=self.root)

    def test_partial_source_fails(self):
        self.valid_pair()
        (self.root / (DAY + ".png")).unlink()
        with self.assertRaisesRegex(SourceMissing, "absent"):
            audit_source(date_sast=DAY, directory=self.root)

    def test_corruption_fails(self):
        self.valid_pair()
        (self.root / (DAY + ".png")).write_bytes(PNG+b"x")
        with self.assertRaisesRegex(SourceMissing, "checksum"):
            audit_source(date_sast=DAY, directory=self.root)

    def test_invalid_status_or_timing_fails(self):
        original = self.valid_pair()
        path = self.root / (DAY + ".json")
        for change in ({"status": "NOT_VALIDATED"},
                       {"target_sast": "2026-11-23T14:30:00+02:00"},
                       {"checked_at_sast": "2026-11-24T14:32:00+02:00"}):
            payload = dict(original, **change)
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(SourceMissing):
                audit_source(date_sast=DAY, directory=self.root)

    def test_no_data_outside_published_folder(self):
        self.valid_pair()
        result = audit_source(date_sast=DAY, directory=self.root)
        self.assertNotIn("access_token", str(result))
        self.assertNotIn("published_post_id", str(result))

if __name__ == "__main__":
    unittest.main()
