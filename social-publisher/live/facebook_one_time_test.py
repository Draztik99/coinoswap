"""One public, clearly marked Facebook API test. Never scheduled or auto-retried.

Only intended for manually approved release testing with the CoinoSwap Page.
Distinct from daily-rate campaigns and their Metricool schedules.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facebook_health import _RejectRedirects, _safe_token, GRAPH_ME_URL
from facebook_page_auth import COINOSWAP_PAGE_ID, confirm_page_token_identity
from facebook_page_readback import PAGE_POSTS_URL
from tag_ledger import TagReservation, ReservationBlocked, TEST_TAG

GRAPH_VERSION = "v27.0"
FEED_URL = f"https://graph.facebook.com/{GRAPH_VERSION}/{COINOSWAP_PAGE_ID}/feed"
APPROVAL = "I_APPROVE_ONE_LIVE_COINOSWAP_TEST_POST"
MESSAGE = ("CoinoSwap publishing connection test ✅\n\n"
           "We're verifying our direct Facebook publishing integration. "
           "This is a technical test post.")
MAX_BYTES = 65536


@dataclass(frozen=True)
class TestOutcome:
    status: str
    reason: str
    provider_post_id: str | None = None
    permalink: str | None = None


def _read(opener, req) -> dict:
    with opener.open(req, timeout=12) as response:
        if getattr(response, "status", 200) != 200:
            raise ValueError("Meta HTTP status unexpected")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Meta JSON oversized")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Meta returned an invalid response")
    return data


def one_time_test(*, token: str, approval: str, enabled: str,
                  repository: Path, opener=None) -> TestOutcome:
    if approval != APPROVAL or enabled != "true":
        return TestOutcome("BLOCKED", "explicit manual test approval or enable flag missing")
    if not _safe_token(token):
        return TestOutcome("BLOCKED", "Page access token unavailable")
    if opener is None:
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                              _RejectRedirects())
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    try:
        identity = _read(opener, Request(GRAPH_ME_URL, headers=headers, method="GET"))
        confirm_page_token_identity(identity)
        feed = _read(opener, Request(PAGE_POSTS_URL, headers=headers, method="GET"))
        records = feed.get("data")
        if not isinstance(records, list) or feed.get("paging", {}).get("next"):
            return TestOutcome("BLOCKED", "Page readback incomplete; do not risk duplication")
        if any(isinstance(p, dict) and p.get("message") == MESSAGE for p in records):
            return TestOutcome("BLOCKED", "test post already exists on the Page")
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError, KeyError):
        return TestOutcome("BLOCKED", "Page ownership or prior posts could not be verified")
    try:
        tag = TagReservation(repository).reserve_one_time_test()
        if tag != TEST_TAG:
            return TestOutcome("BLOCKED", "reservation was not confirmed")
    except (ReservationBlocked, OSError, ValueError):
        return TestOutcome("BLOCKED", "test already reserved or repository reservation unavailable")

    req = Request(FEED_URL, data=urlencode({"message": MESSAGE}).encode("utf-8"),
                  headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                  method="POST")
    try:
        created = _read(opener, req)
        post_id = created.get("id")
        if not isinstance(post_id, str) or re.fullmatch(
            re.escape(COINOSWAP_PAGE_ID) + r"_[0-9]+", post_id
        ) is None:
            raise ValueError("Page post ID absent or mismatched")
        url = (f"https://graph.facebook.com/{GRAPH_VERSION}/" + post_id +
               "?fields=id%2Cmessage%2Cfrom%7Bid%7D%2Cpermalink_url")
        verified = _read(opener, Request(url, headers=headers, method="GET"))
        if (verified.get("id") != post_id or verified.get("message") != MESSAGE
                or not isinstance(verified.get("from"), dict)
                or verified["from"].get("id") != COINOSWAP_PAGE_ID):
            raise ValueError("independent readback mismatch")
        link = verified.get("permalink_url")
        if not isinstance(link, str):
            raise ValueError("no permalink")
        parsed = urlsplit(link)
        if (parsed.scheme != "https"
                or parsed.hostname not in {"www.facebook.com", "facebook.com", "m.facebook.com"}
                or parsed.username or parsed.password or not parsed.path.strip("/")
                or parsed.fragment):
            raise ValueError("invalid public permalink")
        return TestOutcome("VERIFIED", "one live test post independently read back", post_id, link)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError, KeyError, UnicodeError):
        return TestOutcome("UNKNOWN", "test date reserved; reconcile Page manually, NEVER retry")


def main() -> int:
    environment = os.environ
    if environment.get("GITHUB_REF") != "refs/heads/main" or environment.get("GITHUB_REPOSITORY") != "Draztik99/coinoswap":
        print(json.dumps(asdict(TestOutcome("BLOCKED", "main-branch GitHub runner required"))))
        return 2
    result = one_time_test(
        token=environment.get("COINOSWAP_FB_PAGE_ACCESS_TOKEN", ""),
        approval=environment.get("TEST_APPROVAL", ""),
        enabled=environment.get("COINOSWAP_FB_TEST_ENABLED", ""),
        repository=Path.cwd(),
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status == "VERIFIED" else 3 if result.status == "UNKNOWN" else 2


if __name__ == "__main__":
    sys.exit(main())
