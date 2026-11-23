"""Provider post existence verification contracts; offline request descriptions.

A successful X media upload, FB photo upload or Instagram media container
does NOT count as a confirmed published social post. Verification requires
a separate GET response (mocked by tests until API credentials are approved).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from contracts import ContractRejected, RequestSpec, META_API_VERSION


@dataclass(frozen=True)
class VerifiedReceipt:
    platform: str
    provider_post_id: str
    public_url: str


def _number(value: object, label: str) -> str:
    if not isinstance(value,str) or re.fullmatch(r"[0-9]{1,25}",value) is None:
        raise ContractRejected(label+" must be numeric")
    return value


def _permalink(value: object, hosts: set[str]) -> str:
    if not isinstance(value,str):
        raise ContractRejected("public permalink missing")
    parts=urlsplit(value)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in hosts:
        raise ContractRejected("public permalink has unexpected host")
    if parts.username or parts.password or not parts.path.strip("/"):
        raise ContractRejected("public permalink malformed")
    return value


def x_verify_spec(post_id: str) -> RequestSpec:
    return RequestSpec(
        "x","verify_post","GET",
        "https://api.x.com/2/tweets/"+_number(post_id,"X post ID"),
        {"tweet.fields":"author_id,created_at"},
    )


def facebook_verify_spec(photo_id: str) -> RequestSpec:
    return RequestSpec(
        "facebook","verify_photo","GET",
        f"https://graph.facebook.com/{META_API_VERSION}/"+_number(photo_id,"FB photo ID"),
        {"fields":"id,page_story_id,link"},
    )


def instagram_verify_spec(media_id: str) -> RequestSpec:
    return RequestSpec(
        "instagram","verify_media","GET",
        f"https://graph.facebook.com/{META_API_VERSION}/"+_number(media_id,"IG media ID"),
        {"fields":"id,permalink,media_type"},
    )


def verify_x_post(expected_id: str, expected_author_id: str, author_handle: str, response: dict) -> VerifiedReceipt:
    """No claim of publication unless the read-back matches owner+post ID."""
    expected_id=_number(expected_id,"X post ID")
    expected_author_id=_number(expected_author_id,"X author ID")
    if not isinstance(author_handle,str) or not re.fullmatch(r"[A-Za-z0-9_]{1,15}",author_handle):
        raise ContractRejected("invalid verified X account handle")
    item=response.get("data") if isinstance(response,dict) else None
    if not isinstance(item,dict) or item.get("id")!=expected_id or item.get("author_id")!=expected_author_id:
        raise ContractRejected("X post not confirmed on expected account")
    return VerifiedReceipt("x",expected_id, f"https://x.com/{author_handle}/status/{expected_id}")


def verify_facebook_photo(expected_photo_id: str, response: dict) -> VerifiedReceipt:
    photo_id=_number(expected_photo_id,"FB photo ID")
    if not isinstance(response,dict) or response.get("id")!=photo_id:
        raise ContractRejected("Facebook photo not confirmed")
    story_id=response.get("page_story_id")
    if not isinstance(story_id,str) or not re.fullmatch(r"[0-9]+_[0-9]+",story_id):
        raise ContractRejected("Facebook Page post is not verified")
    link=_permalink(response.get("link"),{"facebook.com","www.facebook.com","m.facebook.com"})
    return VerifiedReceipt("facebook",story_id,link)


def verify_instagram_media(expected_media_id: str, response: dict) -> VerifiedReceipt:
    media_id=_number(expected_media_id,"IG media ID")
    if (not isinstance(response,dict) or response.get("id")!=media_id
        or response.get("media_type")!="IMAGE"):
        raise ContractRejected("Instagram published image not confirmed")
    link=_permalink(response.get("permalink"),{"instagram.com","www.instagram.com"})
    return VerifiedReceipt("instagram",media_id,link)
