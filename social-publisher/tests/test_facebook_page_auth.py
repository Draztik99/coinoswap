"""Pure offline Facebook Page preflight tests (no Meta calls)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import ContractRejected
from facebook_page_auth import (
    COINOSWAP_PAGE_ID,
    audit_page_access,
    page_access_lookup_spec,
    page_identity_lookup_spec,
    confirm_page_token_identity,
)


class FacebookPageAuthTests(unittest.TestCase):
    def test_lookup_is_get_only_and_has_no_credentials(self):
        spec = page_access_lookup_spec()
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.operation, "lookup_page_access")
        self.assertEqual(spec.url, "https://graph.facebook.com/v27.0/me/accounts")
        self.assertEqual(spec.body["fields"], "id,name,tasks,access_token")
        self.assertNotIn("authorization", str(spec).lower())

    def test_valid_page_and_secret_never_returned(self):
        secret = "EAAG_PRIVATE_TEST_SECRET_123"
        response = {"data": [
            {"id": "999", "name": "Another Page", "access_token": secret},
            {"id": COINOSWAP_PAGE_ID, "name": "Coinoswap",
             "tasks": ["CREATE_CONTENT", "ANALYZE"], "access_token": secret},
        ]}
        audit = audit_page_access(response)
        self.assertEqual(audit.page_name, "Coinoswap")
        self.assertTrue(audit.has_create_content_task)
        self.assertTrue(audit.has_page_access_token)
        self.assertTrue(audit.can_proceed_to_safe_token_verification)
        self.assertNotIn(secret, repr(audit))
        self.assertNotIn(secret, str(audit))

    def test_no_token_is_not_ready(self):
        audit = audit_page_access({"data": [
            {"id": COINOSWAP_PAGE_ID, "name": "Coinoswap",
             "tasks": ["CREATE_CONTENT"]}
        ]})
        self.assertFalse(audit.can_proceed_to_safe_token_verification)

    def test_no_create_content_is_not_ready(self):
        audit = audit_page_access({"data": [
            {"id": COINOSWAP_PAGE_ID, "name": "Coinoswap",
             "tasks": ["ANALYZE"], "access_token": "test-secret"}
        ]})
        self.assertFalse(audit.has_create_content_task)
        self.assertFalse(audit.can_proceed_to_safe_token_verification)

    def test_bad_data_rejected_without_leaking_secret(self):
        invalid = [
            {"error": {"message": "private example"}},
            {"data": []},
            {"data": [{"id": COINOSWAP_PAGE_ID, "name": ""}]},
            {"data": [{"id": COINOSWAP_PAGE_ID, "name": "Coinoswap", "tasks": "CREATE_CONTENT"}]},
            {"data": [{"id": COINOSWAP_PAGE_ID, "name": "Coinoswap"},
                      {"id": COINOSWAP_PAGE_ID, "name": "Coinoswap"}]},
        ]
        for payload in invalid:
            with self.subTest(payload=type(payload)):
                with self.assertRaises(ContractRejected) as caught:
                    audit_page_access(payload)
                self.assertNotIn("private example", str(caught.exception))

    def test_new_page_task_alias(self):
        audit = audit_page_access({"data": [
            {"id": COINOSWAP_PAGE_ID, "name": "Coinoswap",
             "tasks": ["PROFILE_PLUS_CREATE_CONTENT"], "access_token": "secret"}
        ]})
        self.assertTrue(audit.can_proceed_to_safe_token_verification)


    def test_page_token_identity_must_be_exact_coinoswap_page(self):
        spec = page_identity_lookup_spec()
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.url, "https://graph.facebook.com/v27.0/me")
        self.assertEqual(spec.body, {"fields": "id,name"})
        self.assertEqual(confirm_page_token_identity({
            "id": COINOSWAP_PAGE_ID, "name": "Coinoswap"
        }), "Coinoswap")
        for invalid in [
            {"id": "123", "name": "Another Page"},
            {"id": COINOSWAP_PAGE_ID},
            {"error": {"message": "private-token-value"}},
        ]:
            with self.subTest(response_shape=list(invalid.keys())):
                with self.assertRaises(ContractRejected) as caught:
                    confirm_page_token_identity(invalid)
                self.assertNotIn("private-token-value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
