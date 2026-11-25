"""Read-only CoinoSwap Facebook Page published-posts preflight.

This diagnostic uses one exact Meta Graph GET and the existing protected Page
secret. It NEVER publishes, reserves a date or prints a token/provider body.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPSHandler, ProxyHandler, build_opener

from asset_reader import SAST
from facebook_health import TOKEN_ENV, _RejectRedirects, _safe_token
from facebook_page_readback import PAGE_POSTS_URL
from facebook_reconciliation import scan_published_posts


@dataclass(frozen=True)
class FeedCheck:
    status: str
    http_status: int | None = None
    all_pages_inspected: bool = False
    inspected_count: int = 0


def check_page_feed(*, environ: Mapping[str, str] | None = None,
                    opener=None, now: datetime | None = None) -> FeedCheck:
    values = os.environ if environ is None else environ
    token = values.get(TOKEN_ENV)
    if not _safe_token(token):
        return FeedCheck("TOKEN_NOT_CONFIGURED")
    now = datetime.now(SAST) if now is None else now
    if now.tzinfo is None or now.utcoffset() is None:
        return FeedCheck("INVALID_CLOCK")
    now = now.astimezone(SAST)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    url = PAGE_POSTS_URL + "&" + urlencode({
        "since": int(day.timestamp()),
        "until": int((day + timedelta(days=1)).timestamp()),
    })
    if opener is None:
        opener = build_opener(ProxyHandler({}),
                              HTTPSHandler(context=ssl.create_default_context()),
                              _RejectRedirects())
    request = Request(url, method="GET", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "CoinoSwap-Page-Readback-Preflight/1.0",
    })
    try:
        with opener.open(request, timeout=8) as response:
            if getattr(response, "status", 200) != 200:
                return FeedCheck("PAGE_FEED_NON_SUCCESS")
            blob = response.read(128_001)
        if len(blob) > 128_000:
            return FeedCheck("PAGE_FEED_RESPONSE_TOO_LARGE")
        payload = json.loads(blob.decode("utf-8"))
        audit = scan_published_posts(payload, date_sast=day.date().isoformat())
        if audit.status == "POSSIBLE_DUPLICATE":
            return FeedCheck("PAGE_FEED_POSSIBLE_DUPLICATE",
                             all_pages_inspected=audit.all_pages_inspected,
                             inspected_count=audit.inspected_count)
        if audit.all_pages_inspected:
            return FeedCheck("PAGE_FEED_ACCESSIBLE",
                             all_pages_inspected=True,
                             inspected_count=audit.inspected_count)
        return FeedCheck("PAGE_FEED_INCOMPLETE",
                         inspected_count=audit.inspected_count)
    except HTTPError as exc:
        # Only numeric HTTP status leaves this process, never Meta error text.
        return FeedCheck("PAGE_FEED_HTTP_REJECTED", http_status=exc.code)
    except (URLError, OSError, TimeoutError, ValueError, TypeError, UnicodeError):
        return FeedCheck("PAGE_FEED_UNAVAILABLE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Meta Page feed GET-only diagnostic")
    parser.add_argument("--check", action="store_true", help="Perform one read-only GET")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("explicit --check required; no network access performed")
    result = check_page_feed()
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status == "PAGE_FEED_ACCESSIBLE" else 2


if __name__ == "__main__":
    sys.exit(main())
