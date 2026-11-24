"""Explicit GET-only Facebook Page token health probe.

A manual diagnostic, NOT an OAuth exchange, publication adapter or scheduler.
No token is ever returned, printed, persisted or placed in the URL.
Importing this module makes no external requests.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from dataclasses import asdict, dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener,
)

from contracts import ContractRejected, META_API_VERSION
from facebook_page_auth import COINOSWAP_PAGE_ID, confirm_page_token_identity

TOKEN_ENV = "COINOSWAP_FB_PAGE_ACCESS_TOKEN"
GRAPH_ME_URL = f"https://graph.facebook.com/{META_API_VERSION}/me?fields=id%2Cname"
MAX_RESPONSE_BYTES = 16_384
DEFAULT_TIMEOUT_SECONDS = 8


class _RejectRedirects(HTTPRedirectHandler):
    """A redirected request must never forward a bearer token."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class HealthResult:
    status: str
    reason: str
    page_id: str | None = None
    # No token, upstream error text or request headers in this output.


def _safe_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 4096
        and value == value.strip()
        and not any(ord(char) < 33 or ord(char) == 127 for char in value)
    )


def check_page_token(
    *,
    environ: Mapping[str, str] | None = None,
    opener=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> HealthResult:
    """Verify only the token's Page identity via Meta Graph GET /me.

    A successful check is not proof of token lifetime or publishing access.
    For production, use a reviewed secrets store, permission/expiry checks,
    separate publishing approval and cross-publisher duplicate protection.
    """
    if environ is None:
        environ = os.environ
    token = environ.get(TOKEN_ENV)
    if token is None:
        return HealthResult("NOT_CONFIGURED", "Page token environment secret not configured")
    if not _safe_token(token):
        return HealthResult("INVALID_CONFIGURATION", "Page token secret has invalid format")
    if not isinstance(timeout, int) or not 1 <= timeout <= 30:
        return HealthResult("INVALID_CONFIGURATION", "Timeout must be 1-30 seconds")

    request = Request(
        GRAPH_ME_URL,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "CoinoSwap-Facebook-Identity-Health/1.0",
        },
        method="GET",
    )
    # Exactly one fixed HTTPS URL; custom transport is mockable offline.
    if opener is None:
        opener = build_opener(
            ProxyHandler({}),
            HTTPSHandler(context=ssl.create_default_context()),
            _RejectRedirects(),
        )
    try:
        with opener.open(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return HealthResult("API_ERROR", "Meta returned a non-success status")
            content = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            return HealthResult("REDIRECT_BLOCKED", "Unexpected Meta redirect refused")
        if exc.code in (400, 401, 403):
            return HealthResult("AUTH_REJECTED", "Meta rejected Page token or access")
        if exc.code == 429:
            return HealthResult("RATE_LIMITED", "Meta rate limit; no retry attempted")
        return HealthResult("API_ERROR", "Meta returned a non-success status")
    except (URLError, OSError, TimeoutError, ValueError):
        return HealthResult("NETWORK_ERROR", "Graph identity request failed")
    # Never return or log the original exception, body or credentials.
    if len(content) > MAX_RESPONSE_BYTES:
        return HealthResult("UNEXPECTED_RESPONSE", "Graph identity response too large")
    try:
        response_data = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return HealthResult("UNEXPECTED_RESPONSE", "Graph identity response invalid")
    try:
        confirm_page_token_identity(response_data)
    except ContractRejected:
        return HealthResult("IDENTITY_MISMATCH", "Token is not confirmed for CoinoSwap Page")
    return HealthResult("VERIFIED_PAGE_IDENTITY", "Read-only Page identity matched", COINOSWAP_PAGE_ID)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual GET-only CoinoSwap Page identity check")
    parser.add_argument("--check", action="store_true", help="Make a single read-only Graph GET")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("explicit --check required; no request was made")
    result = check_page_token()
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status == "VERIFIED_PAGE_IDENTITY" else 2


if __name__ == "__main__":
    sys.exit(main())
