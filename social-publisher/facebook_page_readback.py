"""Manual read-only Facebook Page post audit, never sends a publish request.

Requires the Page token in the local process environment. Every call is a
strict fixed-URL GET, over verified TLS, with no redirects or retries. It does
not replace Metricool reconciliation or a durable publication ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from asset_reader import SAST
from contracts import ContractRejected
from facebook_health import (
    DEFAULT_TIMEOUT_SECONDS, GRAPH_ME_URL, MAX_RESPONSE_BYTES,
    TOKEN_ENV, _RejectRedirects, _safe_token,
)
from facebook_page_auth import confirm_page_token_identity
from facebook_reconciliation import (
    published_posts_lookup_spec, scan_published_posts,
)

PAGE_POSTS_SPEC = published_posts_lookup_spec()
PAGE_POSTS_URL = PAGE_POSTS_SPEC.url + "?" + urlencode(PAGE_POSTS_SPEC.body)
MAX_PAGE_RESPONSE = 128_000


@dataclass(frozen=True)
class ReadbackResult:
    status: str
    reason: str
    date_sast: str
    possible_post_ids: tuple[str, ...] = ()
    inspected_count: int = 0
    all_pages_inspected: bool = False
    published_posts_created: int = 0


def _get_json(opener, url: str, token: str, max_bytes: int) -> dict:
    if url not in {GRAPH_ME_URL, PAGE_POSTS_URL}:
        raise ValueError("read-only URL not on allowlist")
    request = Request(url, method="GET", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "CoinoSwap-Facebook-ReadOnly-Audit/1.0",
    })
    with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        if getattr(response, "status", 200) != 200:
            raise ValueError("unexpected API response status")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("unexpected API response size")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("unexpected API JSON shape")
    return value


def audit_page_published_posts(
    *, at_sast: datetime | None = None,
    environ: Mapping[str, str] | None = None,
    opener=None,
) -> ReadbackResult:
    now = datetime.now(SAST) if at_sast is None else at_sast
    if now.tzinfo is None or now.utcoffset() is None:
        return ReadbackResult("INVALID_CONFIGURATION", "Timezone required", "")
    day = now.astimezone(SAST).date().isoformat()
    values = os.environ if environ is None else environ
    token = values.get(TOKEN_ENV)
    if token is None:
        return ReadbackResult("NOT_CONFIGURED", "Page token environment secret missing", day)
    if not _safe_token(token):
        return ReadbackResult("INVALID_CONFIGURATION", "Page token secret invalid", day)
    if opener is None:
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                              _RejectRedirects())
    try:
        identity = _get_json(opener, GRAPH_ME_URL, token, MAX_RESPONSE_BYTES)
        confirm_page_token_identity(identity)
        feed = _get_json(opener, PAGE_POSTS_URL, token, MAX_PAGE_RESPONSE)
        result = scan_published_posts(feed, date_sast=day)
        return ReadbackResult(
            status=result.status, reason=result.reason,
            date_sast=day, possible_post_ids=result.possible_post_ids,
            inspected_count=result.inspected_count,
            all_pages_inspected=result.all_pages_inspected,
        )
    except HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            kind = "REDIRECT_BLOCKED"
        elif exc.code in (400, 401, 403):
            kind = "AUTH_REJECTED"
        elif exc.code == 429:
            kind = "RATE_LIMITED"
        else:
            kind = "API_ERROR"
        return ReadbackResult(kind, "Meta GET request did not succeed", day)
    except ContractRejected:
        return ReadbackResult("IDENTITY_MISMATCH", "Page token identity not confirmed", day)
    except (OSError, URLError, TimeoutError, ValueError, TypeError, UnicodeError,
            json.JSONDecodeError):
        return ReadbackResult("UNVERIFIED", "Read-only audit failed or response was incomplete", day)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual Facebook read-only post audit")
    parser.add_argument("--check", action="store_true", help="Do two read-only Meta GET requests")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("explicit --check required")
    report = audit_page_published_posts()
    print(json.dumps(asdict(report), sort_keys=True))
    # Never emit exit code 0 as a misleading clearance to publish.\n    return 3 if report.status == "POSSIBLE_DUPLICATE" else 2


if __name__ == "__main__":
    sys.exit(main())
