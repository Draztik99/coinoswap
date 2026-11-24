"""Contract read-back: uploaded media never counts as published without GET."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from contracts import ContractRejected
from receipts import (
    x_verify_spec, facebook_verify_spec, instagram_verify_spec,
    verify_x_post, verify_facebook_photo, verify_instagram_media,
)


class ReceiptTests(unittest.TestCase):
    def test_all_verification_requests_are_get_only(self):
        requests=(x_verify_spec("1"),facebook_verify_spec("2"),instagram_verify_spec("3"))
        self.assertTrue(all(spec.method=="GET" for spec in requests))
        self.assertEqual(requests[0].body,{"tweet.fields":"author_id,created_at"})
        self.assertEqual(requests[1].body,{"fields":"id,page_story_id,link,from{id}"})

    def test_x_published_post_requires_matching_author(self):
        receipt=verify_x_post("555","123","CoinoSwap",
                              {"data":{"id":"555","author_id":"123","text":"Rates"}})
        self.assertTrue(receipt.public_url.endswith("/status/555"))
        with self.assertRaises(ContractRejected):
            verify_x_post("555","123","CoinoSwap",{"data":{"id":"555","author_id":"456"}})

    def test_x_media_upload_id_is_not_a_confirmed_post(self):
        with self.assertRaises(ContractRejected):
            verify_x_post("555","123","CoinoSwap",{"data":{"id":"555"}})

    def test_fb_photo_id_without_page_post_receipt_rejected(self):
        with self.assertRaisesRegex(ContractRejected,"post is not verified"):
            verify_facebook_photo("456",{"id":"456","link":"https://facebook.com/example/photo/"})

    def test_fb_page_story_and_permalink_confirmed(self):
        receipt=verify_facebook_photo("456",{
            "id":"456","page_story_id":"108130358772133_222",
            "from":{"id":"108130358772133"},
            "link":"https://www.facebook.com/example/posts/222"})
        self.assertEqual(receipt.provider_post_id,"108130358772133_222")


    def test_fb_wrong_page_and_missing_owner_are_rejected(self):
        correct={"id":"456","page_story_id":"108130358772133_222",
                 "from":{"id":"108130358772133"},
                 "link":"https://www.facebook.com/example/posts/222"}
        for invalid in (
            {**correct,"page_story_id":"999_222"},
            {**correct,"from":{"id":"999"}},
            {key:value for key,value in correct.items() if key!="from"},
        ):
            with self.subTest(fields=tuple(invalid.keys())):
                with self.assertRaises(ContractRejected):
                    verify_facebook_photo("456",invalid)

    def test_fb_returned_post_id_must_match_readback(self):
        item={"id":"456","page_story_id":"108130358772133_222",
              "from":{"id":"108130358772133"},
              "link":"https://www.facebook.com/example/posts/222"}
        self.assertEqual(
            verify_facebook_photo("456",item,expected_post_id="108130358772133_222").provider_post_id,
            "108130358772133_222")
        with self.assertRaises(ContractRejected):
            verify_facebook_photo("456",item,expected_post_id="108130358772133_999")

    def test_instagram_upload_container_is_not_media_receipt(self):
        with self.assertRaises(ContractRejected):
            verify_instagram_media("777",{"id":"777"})

    def test_instagram_published_media_and_link(self):
        receipt=verify_instagram_media("777",{
            "id":"777","permalink":"https://www.instagram.com/p/example/",
            "media_type":"IMAGE"})
        self.assertEqual(receipt.provider_post_id,"777")

    def test_instagram_wrong_host_rejected(self):
        with self.assertRaises(ContractRejected):
            verify_instagram_media("777",{
                "id":"777","permalink":"https://attacker.example/p/example/",
                "media_type":"IMAGE"})

    def test_wrong_account_id_rejected(self):
        with self.assertRaises(ContractRejected):
            verify_x_post("999","100","CoinoSwap",{"data":{"id":"999","author_id":"101"}})


if __name__=="__main__":
    unittest.main()
