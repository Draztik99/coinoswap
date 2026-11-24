"""Read-only Facebook published-post audit with conservative duplicate flags.

This module constructs a GET specification and parses already-retrieved Meta
responses. It NEVER executes POST requests or authorizes a scheduled post.
A negative scan is never proof that Metricool has not published elsewhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit

from asset_reader import SAST
from contracts import META_API_VERSION, RequestSpec, ContractRejected
from facebook_page_auth import COINOSWAP_PAGE_ID

POST_FIELDS = "id,message,created_time,permalink_url"
PAGE_SIZE = 100
DAILY_RATES_TERMS = ("btc", "eth", "xmr")


@dataclass(frozen=True)
class PublicationAudit:
    status: str
    reason: str
    date_sast: str
    possible_post_ids: tuple[str, ...]
    inspected_count: int
    all_pages_inspected: bool
    posts_created: int = 0


def published_posts_lookup_spec() -> RequestSpec:
    return RequestSpec(
        "facebook", "read_page_published_posts", "GET",
        f"https://graph.facebook.com/{META_API_VERSION}/{COINOSWAP_PAGE_ID}/published_posts",
        {"fields": POST_FIELDS, "limit": PAGE_SIZE},
    )


def _date(value: str) -> str:
    if not isinstance(value, str):
        raise ContractRejected("invalid audit date")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractRejected("invalid audit date") from exc
    if d.isoformat() != value:
        raise ContractRejected("noncanonical audit date")
    return value


def scan_published_posts(response: dict, *, date_sast: str) -> PublicationAudit:
    """Flags plausible CoinoSwap Daily Rates posts, never establishes no duplicate.

    A Page post's message alone is not proof of a match: photos and Metricool
    posts may omit the expected words, and pagination or permissions can hide
    records. Only *positive* candidate detection is actionable.
    """
    day = _date(date_sast)
    if not isinstance(response, dict) or response.get("error"):
        return PublicationAudit("UNVERIFIED", "Graph response unavailable or rejected",
                                day, (), 0, False)
    data = response.get("data")
    if not isinstance(data, list) or len(data) > PAGE_SIZE:
        return PublicationAudit("UNVERIFIED", "Graph post list malformed or oversized",
                                day, (), 0, False)
    paging = response.get("paging")
    if paging is not None and not isinstance(paging, dict):
        return PublicationAudit("UNVERIFIED", "Graph pagination metadata malformed",
                                day, (), 0, False)
    complete = not bool((paging or {}).get("next"))
    candidates = []
    inspected = 0
    missing_fields = False
    for post in data:
        if not isinstance(post, dict):
            missing_fields = True
            continue
        pid, published_at, message = (post.get("id"), post.get("created_time"),
                                      post.get("message"))
        if not isinstance(pid, str) or re.fullmatch(r"[0-9]+_[0-9]+", pid) is None:
            missing_fields = True
            continue
        if not pid.startswith(COINOSWAP_PAGE_ID + "_"):
            missing_fields = True
            continue
        try:
            parsed = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError):
            missing_fields = True
            continue
        if parsed.astimezone(SAST).date().isoformat() != day:
            continue
        inspected += 1
        if not isinstance(message, str):
            missing_fields = True
            continue
        normalized = message.casefold()
        if all(re.search(r"(?<![a-z])" + word + r"(?![a-z])", normalized)
               for word in DAILY_RATES_TERMS):
            candidates.append(pid)
    if candidates:
        return PublicationAudit("POSSIBLE_DUPLICATE",
                                "Daily Rates-like Page posts found; manual review required",
                                day, tuple(candidates), inspected, complete)
    return PublicationAudit(
        "UNVERIFIED",
        "No text match is not proof of no publication; reconcile Metricool receipts"
        if complete and not missing_fields else
        "Graph results incomplete or ambiguous; reconcile before any delivery",
        day, (), inspected, complete and not missing_fields,
    )
