"""PostgreSQL-ready transactional idempotency ledger; no network on import.

The connection is injected by a separately reviewed deployment. No database
connection is initiated in this module, and there is NO Facebook POST transport.
The UNIQUE key is authoritative across workers sharing one PostgreSQL server.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit, parse_qsl

from receipts import VerifiedReceipt
from facebook_page_auth import COINOSWAP_PAGE_ID

from ledger import LedgerError

STATE_TRANSITIONS = frozenset({
    ("RESERVED", "SENDING"),
    ("RESERVED", "FAILED_PRE_SEND"),
    ("SENDING", "UNKNOWN"),
    ("SENDING", "PUBLISHED"),
    ("UNKNOWN", "PUBLISHED"),
})

ALLOWED_ERROR_CODES = frozenset({"AUTH_REJECTED", "RATE_LIMITED", "NETWORK_ERROR", "TIMEOUT", "PROVIDER_ERROR", "RECEIPT_MISSING", "UNEXPECTED_RESPONSE"})

RESERVE_SQL = """
INSERT INTO coinoswap_social_publications
(platform, date_sast, campaign_key, image_sha256, request_id, state, source)
VALUES (%s, %s, %s, %s, %s, 'RESERVED', 'direct')
ON CONFLICT (platform, date_sast, campaign_key) DO NOTHING
RETURNING state
"""
TRANSITION_SQL = """
UPDATE coinoswap_social_publications
SET state=%s, provider_post_id=%s, public_url=%s,
    last_error=%s, updated_at_utc=now()
WHERE platform=%s AND date_sast=%s AND campaign_key=%s AND state=%s AND source='direct'
RETURNING state
"""
EXTERNAL_SQL = """
INSERT INTO coinoswap_social_publications
(platform, date_sast, campaign_key, image_sha256, request_id, state,
 provider_post_id, public_url, source)
VALUES (%s, %s, %s, %s, 'external:metricool', 'PUBLISHED',
        %s, %s, 'metricool')
ON CONFLICT (platform, date_sast, campaign_key) DO NOTHING
RETURNING state
"""


def _key(platform: str, day: str, campaign: str) -> tuple[str, str, str]:
    if platform not in {"facebook", "x", "instagram"}:
        raise LedgerError("unknown platform")
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise LedgerError("invalid SAST date") from exc
    if not isinstance(campaign, str) or re.fullmatch(r"[a-z0-9_-]{2,60}", campaign) is None:
        raise LedgerError("invalid campaign")
    return platform, day, campaign


def _hash(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise LedgerError("invalid image SHA-256")
    return value


@dataclass(frozen=True)
class DurableLedger:
    # connection_factory must yield a DB-API compatible connection whose
    # context manager atomically commits on success and rolls back on errors.
    connection_factory: object

    def _execute_once(self, sql: str, params: tuple) -> bool:
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone() is not None

    def reserve(
        self, platform: str, date_sast: str, campaign_key: str,
        image_sha256: str, request_id: str,
    ) -> bool:
        key = _key(platform, date_sast, campaign_key)
        _hash(image_sha256)
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise LedgerError("invalid request ID")
        return self._execute_once(RESERVE_SQL, (*key, image_sha256, request_id))

    def transition(
        self, platform: str, date_sast: str, campaign_key: str, *,
        from_state: str, to_state: str,
        provider_post_id: str | None = None, public_url: str | None = None,
        error: str | None = None,
        verified_receipt: VerifiedReceipt | None = None,
    ) -> None:
        key = _key(platform, date_sast, campaign_key)
        if (from_state, to_state) not in STATE_TRANSITIONS:
            raise LedgerError("invalid state transition")
        if error is not None and error not in ALLOWED_ERROR_CODES:
            raise LedgerError("only fixed redacted error codes may be persisted")
        if to_state == "PUBLISHED":
            if not isinstance(verified_receipt, VerifiedReceipt):
                raise LedgerError("published state requires a verified receipt object")
            if verified_receipt.platform != platform:
                raise LedgerError("verified receipt platform mismatch")
            if provider_post_id != verified_receipt.provider_post_id or public_url != verified_receipt.public_url:
                raise LedgerError("published receipt fields do not match readback")
            parts = urlsplit(public_url)
            allowed_hosts = {
                "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com"},
                "instagram": {"instagram.com", "www.instagram.com"},
                "x": {"x.com", "www.x.com"},
            }
            if (parts.scheme != "https" or parts.hostname not in allowed_hosts[platform]
                    or parts.username or parts.password or not parts.path.strip("/")
                    or parts.fragment
                    or any(key.casefold() in {"access_token", "token", "secret", "api_key"}
                           for key, _ in parse_qsl(parts.query, keep_blank_values=True))):
                raise LedgerError("invalid verified receipt permalink")
            if platform == "facebook" and (
                not isinstance(provider_post_id, str)
                or re.fullmatch(re.escape(COINOSWAP_PAGE_ID) + r"_[0-9]+", provider_post_id) is None
            ):
                raise LedgerError("verified Facebook receipt is not for CoinoSwap Page")
        elif verified_receipt is not None:
            raise LedgerError("receipt supplied for a non-published state")
        result = self._execute_once(
            TRANSITION_SQL,
            (to_state, provider_post_id, public_url, error, *key, from_state),
        )
        if not result:
            raise LedgerError("missing row or unexpected state")

    def adopt_verified_metricool_receipt(
        self, platform: str, date_sast: str, campaign_key: str,
        image_sha256: str, *,
        provider_post_id: str, public_url: str,
        independently_verified: bool = False,
    ) -> bool:
        """Only a caller that independently verified receipt may adopt it.

        No network verification is done here. Imported receipts are always
        non-overwriting, including when a direct job is RESERVED/UNKNOWN.
        """
        from urllib.parse import urlsplit
        key = _key(platform, date_sast, campaign_key)
        if platform != "facebook":
            raise LedgerError("Facebook-only Metricool reconciliation in this adapter")
        _hash(image_sha256)
        if independently_verified is not True:
            raise LedgerError("external publication must be independently verified")
        if not isinstance(provider_post_id, str) or not provider_post_id.strip():
            raise LedgerError("external post ID required")
        if not isinstance(public_url, str):
            raise LedgerError("external permalink required")
        parts = urlsplit(public_url)
        if parts.scheme != "https" or parts.hostname not in {
            "facebook.com", "www.facebook.com", "m.facebook.com"
        } or parts.username or parts.password:
            raise LedgerError("invalid Facebook external permalink")
        return self._execute_once(
            EXTERNAL_SQL,
            (*key, image_sha256, provider_post_id, public_url),
        )
