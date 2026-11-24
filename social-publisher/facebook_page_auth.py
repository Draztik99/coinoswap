"""Offline Facebook Page authorization audit. Never logs or returns tokens.

This module makes NO API calls and cannot publish. Only accepts the JSON result
from Graph API Explorer /me/accounts and returns a safe summary of the expected
Page. Callers must not print or persist the raw JSON, which can contain secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contracts import ContractRejected, META_API_VERSION, RequestSpec

COINOSWAP_PAGE_ID = "108130358772133"
CREATE_CONTENT_TASKS = frozenset({
    "CREATE_CONTENT",
    "PROFILE_PLUS_CREATE_CONTENT",
    "PROFILE_PLUS_FULL_CONTROL",
})


@dataclass(frozen=True)
class PageAccessPreflight:
    page_id: str
    page_name: str
    has_create_content_task: bool
    has_page_access_token: bool
    can_proceed_to_safe_token_verification: bool


def page_access_lookup_spec() -> RequestSpec:
    """Describe the read-only Graph call; intentionally contains no credentials.

    The result may contain a secret: do not paste, log, or commit its JSON.
    """
    return RequestSpec(
        "facebook",
        "lookup_page_access",
        "GET",
        f"https://graph.facebook.com/{META_API_VERSION}/me/accounts",
        {"fields": "id,name,tasks,access_token"},
    )


def audit_page_access(
    response: dict[str, Any], *, page_id: str = COINOSWAP_PAGE_ID
) -> PageAccessPreflight:
    """Validate the expected Page without ever returning or displaying a token.

    Only a read-only preflight: it cannot prove a token will work or that Meta
    will authorize production posting. No live operation is enabled.
    """
    if not isinstance(page_id, str) or not page_id.isdecimal():
        raise ContractRejected("expected Facebook Page ID must be numeric")
    if not isinstance(response, dict) or response.get("error") is not None:
        raise ContractRejected("Facebook Page lookup failed")
    pages = response.get("data")
    if not isinstance(pages, list):
        raise ContractRejected("Facebook Page lookup returned no Page list")
    matches = [
        row for row in pages
        if isinstance(row, dict) and row.get("id") == page_id
    ]
    if len(matches) != 1:
        raise ContractRejected("expected CoinoSwap Page not found exactly once")
    page = matches[0]
    name = page.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContractRejected("Facebook Page name missing")
    tasks = page.get("tasks")
    if tasks is None:
        tasks = []
    if not isinstance(tasks, list) or any(not isinstance(t, str) for t in tasks):
        raise ContractRejected("Facebook Page tasks field malformed")
    can_create = bool(CREATE_CONTENT_TASKS.intersection(tasks))
    token = page.get("access_token")
    has_token = isinstance(token, str) and bool(token.strip())
    return PageAccessPreflight(
        page_id=page_id,
        page_name=name.strip(),
        has_create_content_task=can_create,
        has_page_access_token=has_token,
        can_proceed_to_safe_token_verification=can_create and has_token,
    )


def page_identity_lookup_spec() -> RequestSpec:
    """Read-only identity check for a token already selected as a Page token."""
    return RequestSpec(
        "facebook",
        "verify_page_token_identity",
        "GET",
        f"https://graph.facebook.com/{META_API_VERSION}/me",
        {"fields": "id,name"},
    )


def confirm_page_token_identity(
    response: dict[str, Any], *, page_id: str = COINOSWAP_PAGE_ID
) -> str:
    """Return a public Page name only if /me identifies the required Page.

    A successful GET identifies the token subject; it does NOT establish
    token lifetime, app live-mode approval or permission to publish.
    """
    if not isinstance(response, dict) or response.get("error") is not None:
        raise ContractRejected("Facebook Page token identity check failed")
    if response.get("id") != page_id:
        raise ContractRejected("Facebook Page token belongs to a different Page")
    name = response.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContractRejected("Facebook Page token returned an invalid Page name")
    return name.strip()
