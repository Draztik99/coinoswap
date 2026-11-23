"""Offline safety tests; no social accounts, tokens, or network required."""
import hashlib
import json
import struct
import sys
import unittest
import zlib
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_reader import AssetRejected, fetch_pinned_pair, validate_asset_pair

NOW = datetime.fromisoformat("2026-11-23T14:49:00+02:00")


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data)) + kind + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def official_size_png():
    """Valid 1536x1024 true-color PNG, built entirely with Python stdlib."""
    width, height = 1536, 1024
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = (b"\x00" + (b"\x00" * (width * 3))) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(scanlines))
        + png_chunk(b"IEND", b"")
    )


def example_audit(image):
    coins = {}
    for sym, p, q in (
        ("BTC", 61183.86685549154, 61133.5),
        ("ETH", 1717.4984626140233, 1715.95),
        ("XMR", 502.6317195808571, 502.34),
    ):
        coins[sym] = {
            "display_usd": round(p, 2),
            "coinmarketcap": {"usd": p, "updated_sast": "2026-11-23T14:45:05+02:00"},
            "kraken": {"usd": q, "updated_sast": "2026-11-23T14:46:23+02:00"},
            "threshold_pct": 2.0 if sym == "XMR" else 1.0,
        }
    return {
        "status": "VALIDATED",
        "approval_state": "NOT_PUBLISHED",
        "date_sast": "2026-11-23",
        "checked_at_sast": "2026-11-23T14:46:25+02:00",
        "target_sast": "2026-11-23T14:49:00+02:00",
        "image": {
            "filename": "2026-11-23.png",
            "sha256": hashlib.sha256(image).hexdigest(),
            "width": 1536,
            "height": 1024,
        },
        "coins": coins,
        "display_prices": {
            sym: "$" + f"{coins[sym]['display_usd']:,.2f}"
            for sym in ("BTC", "ETH", "XMR")
        },
        "caption": "Crypto daily rates. No account needed. coinoswap.com",
    }


class AssetReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = official_size_png()

    def check(self, record=None, *, image=None, now=NOW):
        image = self.image if image is None else image
        record = example_audit(image) if record is None else record
        return validate_asset_pair(
            json.dumps(record).encode("utf-8"), image, now=now
        )

    def test_valid_pinned_style_asset(self):
        data = self.check()
        self.assertEqual(data.date_sast, "2026-11-23")
        self.assertEqual(data.display_prices["XMR"], "$502.63")

    def test_missing_status_is_blocked(self):
        r = example_audit(self.image)
        r["status"] = "NOT_VALIDATED"
        with self.assertRaises(AssetRejected):
            self.check(r)

    def test_image_hash_tampering_is_blocked(self):
        r = example_audit(self.image)
        with self.assertRaisesRegex(AssetRejected, "SHA-256"):
            self.check(r, image=self.image + b"tampered")

    def test_stale_quote_is_blocked(self):
        r = example_audit(self.image)
        r["coins"]["XMR"]["kraken"]["updated_sast"] = "2026-11-23T14:40:00+02:00"
        with self.assertRaisesRegex(AssetRejected, "stale"):
            self.check(r)

    def test_future_quote_is_blocked(self):
        r = example_audit(self.image)
        r["coins"]["ETH"]["kraken"]["updated_sast"] = "2026-11-23T14:49:45+02:00"
        with self.assertRaisesRegex(AssetRejected, "future"):
            self.check(r)

    def test_source_deviation_is_blocked(self):
        r = example_audit(self.image)
        r["coins"]["BTC"]["kraken"]["usd"] = 62500.0
        with self.assertRaisesRegex(AssetRejected, "deviation"):
            self.check(r)

    def test_wrong_day_is_blocked(self):
        r = example_audit(self.image)
        r["date_sast"] = "2026-11-22"
        with self.assertRaisesRegex(AssetRejected, "publication date"):
            self.check(r)

    def test_publication_window_expired(self):
        with self.assertRaisesRegex(AssetRejected, "window expired"):
            self.check(now=NOW + timedelta(seconds=61))

    def test_price_string_must_match_audit(self):
        r = example_audit(self.image)
        r["display_prices"]["ETH"] = "$123"
        with self.assertRaisesRegex(AssetRejected, "price string"):
            self.check(r)

    def test_not_a_png_even_with_matching_hash(self):
        bad = b"not a PNG file"
        r = example_audit(bad)
        with self.assertRaisesRegex(AssetRejected, "not a PNG"):
            self.check(r, image=bad)

    def test_pinned_ref_is_mandatory(self):
        with self.assertRaisesRegex(AssetRejected, "pinned"):
            fetch_pinned_pair(commit_sha="main", date_sast="2026-11-23")

    def test_nan_quote_is_blocked(self):
        r = example_audit(self.image)
        r["coins"]["BTC"]["kraken"]["usd"] = float("nan")
        with self.assertRaises(AssetRejected):
            self.check(r)

    def test_missing_coin_is_blocked(self):
        r = example_audit(self.image)
        del r["coins"]["XMR"]
        with self.assertRaisesRegex(AssetRejected, "coin list"):
            self.check(r)


if __name__ == "__main__":
    unittest.main()
