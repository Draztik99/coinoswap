"""No-network API contract tests against provider-documented schemas."""
import base64
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import (
    ContractRejected, facebook_page_photo, instagram_container_status,
    instagram_create_container, instagram_publish, parse_response_id,
    require_container_finished, x_create_post, x_media_upload,
)


class ContractTests(unittest.TestCase):
    def test_x_png_upload_is_base64_and_category_tweet_image(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"PNG bytes for test"
        spec = x_media_upload(raw)
        self.assertEqual(spec.method, "POST")
        self.assertEqual(spec.url, "https://api.x.com/2/media/upload")
        self.assertEqual(spec.body["media_category"], "tweet_image")
        self.assertEqual(base64.b64decode(spec.body["media"]), raw)

    def test_x_limit_blocks_large_image(self):
        with self.assertRaisesRegex(ContractRejected, "5 MB"):
            x_media_upload(b"\x89PNG\r\n\x1a\n" + b"x" * 5_000_000)

    def test_x_post_attaches_media_once(self):
        spec = x_create_post("BTC ETH XMR coinoswap.com", "12345")
        self.assertEqual(spec.url, "https://api.x.com/2/tweets")
        self.assertEqual(spec.body["media"]["media_ids"], ["12345"])

    def test_x_caption_conservative_limit(self):
        with self.assertRaisesRegex(ContractRejected, "caption"):
            x_create_post("x" * 241, "1")

    def test_fb_photo_contract(self):
        spec = facebook_page_photo(
            "123", "Crypto rates", "https://raw.githubusercontent.com/Draztik99/coinoswap/ABC/2026-11-23.png"
        )
        self.assertEqual(spec.url, "https://graph.facebook.com/v27.0/123/photos")
        self.assertTrue(spec.body["published"])

    def test_fb_rejects_local_http_url(self):
        with self.assertRaisesRegex(ContractRejected, "HTTPS"):
            facebook_page_photo("123", "Crypto rates", "http://127.0.0.1/asset.png")

    def test_fb_rejects_host_ip_even_if_https(self):
        with self.assertRaisesRegex(ContractRejected, "public DNS"):
            facebook_page_photo("123", "Crypto rates", "https://127.0.0.1/x.png")

    def test_ig_requires_hosted_jpeg_and_two_stages(self):
        spec = instagram_create_container("999", "Rates", "https://assets.coinoswap.example/rates/123.jpg")
        self.assertEqual(spec.body["media_type"], "IMAGE")
        self.assertEqual(spec.body["image_url"].split(".")[-1], "jpg")
        status = instagram_container_status("876")
        self.assertEqual(status.method, "GET")
        self.assertEqual(status.body["fields"], "status_code")
        final = instagram_publish("999", "876")
        self.assertTrue(final.url.endswith("/media_publish"))
        self.assertEqual(final.body, {"creation_id": "876"})

    def test_ig_rejects_png_url(self):
        with self.assertRaisesRegex(ContractRejected, "jpg"):
            instagram_create_container("999", "Rates", "https://assets.coinoswap.example/rates.png")

    def test_ig_container_requires_finished(self):
        with self.assertRaisesRegex(ContractRejected, "not ready"):
            require_container_finished({"status_code": "IN_PROGRESS"})
        require_container_finished({"status_code": "FINISHED"})

    def test_ig_rejects_bad_ids(self):
        with self.assertRaisesRegex(ContractRejected, "numeric ID"):
            instagram_publish("ig-handle", "123")

    def test_receipt_upload_not_post(self):
        mid = parse_response_id("media_upload", {"data": {"id": "1234"}})
        self.assertEqual(mid, "1234")
        pid = parse_response_id("create_post", {"data": {"id": "5678"}})
        self.assertNotEqual(mid, pid)

    def test_missing_or_error_receipts_rejected(self):
        for payload in ({}, {"data": {}}, {"data": {"id": "x"}}, {"error": {"code": 190}}):
            with self.subTest(payload=payload):
                with self.assertRaises(ContractRejected):
                    parse_response_id("create_post", payload)

    def test_specs_have_no_transport_credentials(self):
        spec = x_create_post("Rates", "23")
        self.assertFalse(hasattr(spec, "authorization"))
        self.assertNotIn("access_token", spec.body)


if __name__ == "__main__":
    unittest.main()
