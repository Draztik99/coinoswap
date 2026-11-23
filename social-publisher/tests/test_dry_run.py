"""Dry-run integration smoke tests: no API calls and zero posts."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dry_run import main
from test_asset_reader import NOW, example_audit, official_size_png


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.image = official_size_png()
        self.audit_path = self.folder / "2026-11-23.json"
        self.image_path = self.folder / "2026-11-23.png"
        self.audit_path.write_text(json.dumps(example_audit(self.image)), encoding="utf-8")
        self.image_path.write_bytes(self.image)

    def tearDown(self):
        self.temp.cleanup()

    def call_preflight(self, when=NOW.isoformat()):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--audit", str(self.audit_path),
                "--image", str(self.image_path),
                "--at-sast", when,
            ])
        return result, json.loads(output.getvalue())

    def test_passed_preflight_still_creates_zero_social_posts(self):
        code, result = self.call_preflight()
        self.assertEqual(code, 0)
        self.assertEqual(result["result"], "VALIDATED_PREVIEW_ONLY")
        self.assertEqual(result["social_posts_created"], 0)
        self.assertEqual(result["platforms"]["x"], "WOULD_PREPARE_ONLY")
        self.assertEqual(result["platforms"]["instagram"], "WOULD_PREPARE_ONLY")

    def test_expired_preflight_fails_closed(self):
        code, result = self.call_preflight("2026-11-23T18:00:00+02:00")
        self.assertEqual(code, 2)
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["social_posts_created"], 0)

    def test_tampered_asset_fails_closed(self):
        self.image_path.write_bytes(self.image + b"tamper")
        code, result = self.call_preflight()
        self.assertEqual(code, 2)
        self.assertIn("SHA-256", result["reason"])

    def test_fixture_override_requires_explicit_timezone(self):
        with self.assertRaises(SystemExit) as error:
            self.call_preflight("2026-11-23T14:49:00")
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
