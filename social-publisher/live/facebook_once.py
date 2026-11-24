"""Manual, one-attempt Facebook Page photo sender. No automatic schedule.

This module only sends after a separate, durable Git tag reservation succeeds,
a current official asset validates, Facebook Page identity is confirmed, and
a human-approved Metricool Facebook cutover is declared. No POST on import,
tests, shadow runs or without an explicit manual approval.
"""
from __future__ import annotations

import json
import re
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from asset_reader import SAST, ValidatedAsset
from contracts import ContractRejected, META_API_VERSION, facebook_page_photo
from facebook_health import GRAPH_ME_URL, _RejectRedirects, _safe_token
from facebook_page_auth import COINOSWAP_PAGE_ID, confirm_page_token_identity
from facebook_page_readback import PAGE_POSTS_URL
from facebook_reconciliation import scan_published_posts
from receipts import facebook_verify_spec, verify_facebook_photo

from tag_ledger import ReservationBlocked

APPROVAL_PHRASE = "I_APPROVE_SINGLE_COINOSWAP_FB_POST"
MAX_BYTES = 128_000
PAGE_POST_ENDPOINT = f"https://graph.facebook.com/{META_API_VERSION}/{COINOSWAP_PAGE_ID}/photos"


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    reason: str
    page_id: str = COINOSWAP_PAGE_ID
    reservation_tag: str | None = None
    provider_post_id: str | None = None
    public_url: str | None = None


def _get_json(opener, url: str, token: str, *, allowed: set[str]) -> dict:
    if url not in allowed:
        raise ValueError("readback URL not allowed")
    request = Request(
        url, method="GET",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with opener.open(request, timeout=8) as response:
        if getattr(response, "status", 200) != 200:
            raise ValueError("Graph readback status failed")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Graph readback exceeded size")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict) or value.get("error") is not None:
        raise ValueError("Graph readback invalid")
    return value


def publish_once(
    asset: ValidatedAsset, *, pinned_commit: str,
    token: str, environ: Mapping[str, str], approval_phrase: str,
    reservation, opener=None, clock: Callable[[], datetime] | None = None,
) -> DeliveryResult:
    """At most one POST, only after unique reservation succeeds.

    Intentional fail-closed UNKNOWN after post attempt. NEVER automatically
    retry an uncertain delivery. Remote tag survives all errors.
    """
    if approval_phrase != APPROVAL_PHRASE:
        return DeliveryResult("BLOCKED", "explicit manual publishing approval missing")
    if (environ.get("COINOSWAP_FB_LIVE_ENABLED") != "true"
            or environ.get("COINOSWAP_METRICOOL_FB_DISABLED") != "confirmed"):
        return DeliveryResult("BLOCKED", "live switch/cutover confirmation not configured")
    if not _safe_token(token):
        return DeliveryResult("BLOCKED", "Page token missing or invalid format")
    if not isinstance(pinned_commit, str) or re.fullmatch(r"[0-9a-fA-F]{40}", pinned_commit) is None:
        return DeliveryResult("BLOCKED", "immutable main commit SHA required")
    if not isinstance(asset, ValidatedAsset):
        return DeliveryResult("BLOCKED", "official validated image is required")
    if not isinstance(asset.image_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", asset.image_sha256) is None:
        return DeliveryResult("BLOCKED", "validated image digest unavailable")
    if clock is None:
        clock = lambda: datetime.now(SAST)
    try:
        now = clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock not timezone-aware")
        target = datetime.fromisoformat(asset.target_sast).astimezone(SAST)
        current = now.astimezone(SAST)
        if (asset.date_sast != current.date().isoformat()
                or target.date().isoformat() != asset.date_sast
                or not 0 <= (current - target).total_seconds() <= 60):
            return DeliveryResult("BLOCKED", "current SAST posting window expired/not yet open")
        image_url = (
            "https://raw.githubusercontent.com/Draztik99/coinoswap/"
            + pinned_commit + "/docs/daily-rates/" + asset.date_sast + ".png"
        )
        prepared = facebook_page_photo(COINOSWAP_PAGE_ID, asset.caption, image_url)
        if prepared.method != "POST" or prepared.url != PAGE_POST_ENDPOINT:
            return DeliveryResult("BLOCKED", "photo request contract rejected")
    except (ContractRejected, ValueError, TypeError, AttributeError):
        return DeliveryResult("BLOCKED", "validated content preflight failed")
    if opener is None:
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                              _RejectRedirects())
    try:
        confirm_page_token_identity(_get_json(opener, GRAPH_ME_URL, token, allowed={GRAPH_ME_URL}))
        feed = _get_json(opener, PAGE_POSTS_URL, token, allowed={PAGE_POSTS_URL})
        audit = scan_published_posts(feed, date_sast=asset.date_sast)
        if audit.status == "POSSIBLE_DUPLICATE":
            return DeliveryResult("BLOCKED", "possible Facebook daily-rates duplicate exists")
        if not audit.all_pages_inspected:
            return DeliveryResult("BLOCKED", "Page publication readback incomplete")
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, ContractRejected):
        return DeliveryResult("BLOCKED", "Page token identity or readback unverified")
    # A clean readback alone is NOT proof against Metricool duplicates.
    # The separate manual cutover confirmation and immutable Git tag are
    # both required; no other publisher can safely overlap.
    try:
        now = clock()
        if now.tzinfo is None or now.utcoffset() is None or not 0 <= (
            now.astimezone(SAST) - target
        ).total_seconds() <= 60:
            return DeliveryResult("BLOCKED", "posting window expired before reservation")
        tag = reservation.reserve(asset.date_sast)
        if tag != "coinoswap-facebook-daily-rates-" + asset.date_sast:
            return DeliveryResult("BLOCKED", "reservation record not confirmed")
    except ReservationBlocked:
        return DeliveryResult("BLOCKED", "durable reservation unavailable or already exists")
    except (OSError, ValueError, TypeError):
        return DeliveryResult("BLOCKED", "durable reservation failed")
    # An irreversible reservation can outlive the scheduled slot. If the
    # tag push consumed too much time, do not send late; retain the tag.
    try:
        just_before_send = clock()
        if (just_before_send.tzinfo is None or just_before_send.utcoffset() is None
                or not 0 <= (just_before_send.astimezone(SAST) - target).total_seconds() <= 60):
            return DeliveryResult("RESERVED_NO_POST", "reservation held; posting window elapsed",
                                  reservation_tag=tag)
    except (ValueError, TypeError, AttributeError):
        return DeliveryResult("RESERVED_NO_POST", "reservation held; clock unavailable",
                              reservation_tag=tag)
    body = urlencode({
        "url": prepared.body["url"],
        "caption": prepared.body["caption"],
        "published": "true",
    }).encode("utf-8")
    req = Request(
        PAGE_POST_ENDPOINT, method="POST", data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with opener.open(req, timeout=15) as response:
            if getattr(response, "status", 200) != 200:
                raise ValueError("POST non-success")
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("POST response oversized")
        posted = json.loads(raw.decode("utf-8"))
        if not isinstance(posted, dict) or posted.get("error"):
            raise ValueError("POST receipt invalid")
        photo_id = posted.get("id")
        if not isinstance(photo_id, str) or not re.fullmatch(r"[0-9]{1,25}", photo_id):
            raise ValueError("POST photo receipt missing")
        spec = facebook_verify_spec(photo_id)
        read_url = spec.url + "?" + urlencode(spec.body)
        photo = _get_json(opener, read_url, token, allowed={read_url})
        receipt = verify_facebook_photo(photo_id, photo)
        return DeliveryResult("PUBLISHED", "Facebook Page photo independently verified",
                              reservation_tag=tag, provider_post_id=receipt.provider_post_id,
                              public_url=receipt.public_url)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, ContractRejected,
            UnicodeError, json.JSONDecodeError, TypeError):
        return DeliveryResult("UNKNOWN", "reserved date; delivery outcome requires manual reconciliation",
                              reservation_tag=tag)
