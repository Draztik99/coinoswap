"""Offline Meta token-lifecycle assessment from a separately obtained debug response.

Never accepts or returns raw tokens, and makes NO API calls.
Use only within trusted environments; the debug response is untrusted data.
This does not establish authorisation to publish.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

REQUIRED_SCOPES = frozenset({"pages_manage_posts", "pages_read_engagement"})
MIN_REMAINING_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class TokenLifecycleReview:
    status: str
    reason: str
    missing_scopes: tuple[str, ...] = ()
    seconds_until_expiry: int | None = None
    ready_for_live_publishing: bool = False


def review_token_metadata(
    payload: Any, *, expected_app_id: str, now: datetime | None = None
) -> TokenLifecycleReview:
    """Fail closed on an invalid, unknown, or soon-expiring token.

    Meta may report no fixed expiry (`expires_at=0`), which needs explicit
    human / provider review rather than a claim of permanent validity.
    """
    if not isinstance(expected_app_id, str) or not expected_app_id.isdecimal():
        return TokenLifecycleReview("INVALID_CONFIGURATION", "Expected Meta app ID missing")
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return TokenLifecycleReview("INVALID_CONFIGURATION", "A timezone-aware clock is required")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return TokenLifecycleReview("UNVERIFIED", "Meta token-debug response is unavailable")
    data = payload["data"]
    if data.get("is_valid") is not True:
        return TokenLifecycleReview("INVALID", "Meta did not confirm token validity")
    if str(data.get("app_id")) != expected_app_id:
        return TokenLifecycleReview("WRONG_APP", "Token belongs to a different Meta app")
    scopes = data.get("scopes")
    if not isinstance(scopes, list) or any(not isinstance(x, str) for x in scopes):
        return TokenLifecycleReview("UNVERIFIED", "Meta permission metadata unavailable")
    missing = tuple(sorted(REQUIRED_SCOPES - set(scopes)))
    if missing:
        return TokenLifecycleReview("MISSING_SCOPES", "Page publishing permissions incomplete", missing)
    issued = data.get("issued_at")
    expiration = data.get("expires_at")
    if not isinstance(expiration, int) or isinstance(expiration, bool) or expiration < 0:
        return TokenLifecycleReview("UNVERIFIED", "Meta token expiration unavailable")
    if issued is not None and (isinstance(issued, bool) or not isinstance(issued, int) or issued < 0):
        return TokenLifecycleReview("UNVERIFIED", "Meta token issue date invalid")
    if expiration == 0:
        return TokenLifecycleReview("REVIEW_REQUIRED", "No fixed token expiry reported; check invalidation conditions")
    remaining = expiration - int(now.timestamp())
    if remaining <= 0:
        return TokenLifecycleReview("EXPIRED", "Token has passed its reported expiration", seconds_until_expiry=0)
    if remaining < MIN_REMAINING_SECONDS:
        return TokenLifecycleReview("EXPIRING_SOON", "Reported token expiry is within seven days",
                                    seconds_until_expiry=remaining)
    data_expiration = data.get("data_access_expires_at")
    if data_expiration is None or data_expiration == 0:
        return TokenLifecycleReview("REVIEW_REQUIRED", "Meta data-access expiration must be reviewed",
                                    seconds_until_expiry=remaining)
    if isinstance(data_expiration, bool) or not isinstance(data_expiration, int) or data_expiration < 0:
        return TokenLifecycleReview("UNVERIFIED", "Meta data-access expiration invalid")
    data_remaining = data_expiration - int(now.timestamp())
    if data_remaining <= 0:
        return TokenLifecycleReview("DATA_ACCESS_EXPIRED", "Meta data-access window has expired",
                                    seconds_until_expiry=remaining)
    if data_remaining < MIN_REMAINING_SECONDS:
        return TokenLifecycleReview("DATA_ACCESS_EXPIRING_SOON", "Data-access window is within seven days",
                                    seconds_until_expiry=remaining)
    return TokenLifecycleReview("VALIDITY_WINDOW_OK", "Current validity windows verified; publishing NOT authorized",
                                seconds_until_expiry=remaining)
