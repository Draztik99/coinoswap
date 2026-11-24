"""Real, read-only official image conversion and integrity checks."""
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "social-publisher"))
from media_assets import MediaRejected, prepare_media


class MediaAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "docs/daily-rates/2026-11-23.png").read_bytes()
        cls.audit = json.loads((ROOT / "docs/daily-rates/2026-11-23.json").read_text("utf-8"))
        cls.digest = cls.audit["image"]["sha256"]

    def test_official_png_digest_is_genuine(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), self.digest)

    def test_real_png_to_instagram_jpeg_keeps_dimensions(self):
        media = prepare_media(self.source, self.digest)
        self.assertEqual((media.width, media.height), (1536, 1024))
        self.assertEqual(media.png_bytes, self.source)
        self.assertEqual(media.png_sha256, self.digest)
        self.assertLess(len(media.png_bytes), 5_000_000)
        self.assertLess(len(media.jpeg_bytes), 8_000_000)
        self.assertNotEqual(media.jpeg_sha256, self.digest)
        with Image.open(io.BytesIO(media.jpeg_bytes)) as jpg:
            self.assertEqual(jpg.format, "JPEG")
            self.assertEqual(jpg.size, (1536, 1024))

    def test_conversion_preserves_original_content_with_small_loss(self):
        media = prepare_media(self.source, self.digest)
        with Image.open(io.BytesIO(media.jpeg_bytes)) as jpeg:
            with Image.open(io.BytesIO(self.source)) as original:
                difference = ImageChops.difference(original.convert("RGB"), jpeg.convert("RGB"))
                mean = sum(ImageStat.Stat(difference).mean) / 3
        self.assertLess(mean, 12, f"JPEG conversion caused unexpectedly large average pixel change: {mean}")

    def test_conversion_is_deterministic(self):
        a = prepare_media(self.source, self.digest)
        b = prepare_media(self.source, self.digest)
        self.assertEqual(a.jpeg_sha256, b.jpeg_sha256)

    def test_reject_wrong_hash(self):
        with self.assertRaisesRegex(MediaRejected, "digest"):
            prepare_media(self.source, "0" * 64)

    def test_reject_corrupted_png_when_hash_matches(self):
        damaged = self.source[:200]  # truncation; checksum matches forged metadata
        with self.assertRaises(MediaRejected):
            prepare_media(damaged, hashlib.sha256(damaged).hexdigest())

    def test_reject_other_image_with_matching_hash(self):
        wrong = b"not image"
        with self.assertRaises(MediaRejected):
            prepare_media(wrong, hashlib.sha256(wrong).hexdigest())


if __name__ == "__main__":
    unittest.main()
