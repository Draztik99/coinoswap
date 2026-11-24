"""Network-free X/Meta publishing request contracts for offline testing.

These builders only describe requests; there is intentionally NO HTTP executor,
credential access, or live publishing switch in this module.
"""
from __future__ import annotations

import base64
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

META_API_VERSION = "v27.0"
X_IMAGE_MAX_BYTES = 5_000_000
FACEBOOK_IMAGE_MAX_BYTES = 10_000_000


class ContractRejected(ValueError):
    pass


@dataclass(frozen=True)
class RequestSpec:
    provider: str
    operation: str
    method: str
    url: str
    body: dict
    # This is a pure description, not an executable transport.


def _id(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,25}", value):
        raise ContractRejected(f"{label} must be a numeric ID")
    return value


def _caption(value: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractRejected("caption missing")
    if "\x00" in value or len(value) > max_length:
        raise ContractRejected("caption invalid/too long")
    return value.strip()


def _https_image_url(value: str, *, extension: str) -> str:
    if not isinstance(value, str):
        raise ContractRejected("image URL required")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ContractRejected("image URL must use public HTTPS without credentials")
    if parts.port not in (None, 443) or parts.fragment:
        raise ContractRejected("unexpected image URL port or fragment")
    host = parts.hostname.lower()
    if host in {"localhost", "host.docker.internal"} or host.endswith(".local"):
        raise ContractRejected("private image URL host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ContractRejected("image URL must use a public DNS hostname")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host or ".." in host:
        raise ContractRejected("malformed image URL host")
    if not parts.path.lower().endswith(extension) or parts.query:
        raise ContractRejected(f"expected immutable public {extension} URL without query")
    return value


def x_media_upload(png: bytes) -> RequestSpec:
    if not isinstance(png, bytes) or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractRejected("X image must be PNG")
    if len(png) > X_IMAGE_MAX_BYTES:
        raise ContractRejected("X PNG exceeds 5 MB")
    return RequestSpec(
        "x", "media_upload", "POST", "https://api.x.com/2/media/upload",
        {"media": base64.b64encode(png).decode("ascii"), "media_category": "tweet_image"},
    )


def x_create_post(caption: str, media_id: str) -> RequestSpec:
    # Conservative preflight limit: X counts links and Unicode differently,
    # final weighted-length validation is required before live transport.
    text = _caption(caption, 240)
    return RequestSpec(
        "x", "create_post", "POST", "https://api.x.com/2/tweets",
        {"text": text, "media": {"media_ids": [_id(media_id, "X media ID")]}},
    )


def facebook_page_photo(page_id: str, caption: str, png_url: str) -> RequestSpec:
    return RequestSpec(
        "facebook", "page_photo", "POST",
        f"https://graph.facebook.com/{META_API_VERSION}/{_id(page_id, 'Facebook Page ID')}/photos",
        {"url": _https_image_url(png_url, extension=".png"),
         "caption": _caption(caption, 2000), "published": True},
    )


def instagram_create_container(ig_id: str, caption: str, jpeg_url: str) -> RequestSpec:
    return RequestSpec(
        "instagram", "media_container", "POST",
        f"https://graph.facebook.com/{META_API_VERSION}/{_id(ig_id, 'Instagram user ID')}/media",
        {"image_url": _https_image_url(jpeg_url, extension=".jpg"),
         "caption": _caption(caption, 2000), "media_type": "IMAGE"},
    )


def instagram_container_status(container_id: str) -> RequestSpec:
    return RequestSpec(
        "instagram", "container_status", "GET",
        f"https://graph.facebook.com/{META_API_VERSION}/{_id(container_id, 'container ID')}",
        {"fields": "status_code"},
    )


def instagram_publish(ig_id: str, container_id: str) -> RequestSpec:
    return RequestSpec(
        "instagram", "media_publish", "POST",
        f"https://graph.facebook.com/{META_API_VERSION}/{_id(ig_id, 'Instagram user ID')}/media_publish",
        {"creation_id": _id(container_id, "container ID")},
    )


def parse_response_id(operation: str, response: dict) -> str:
    """Parse a provider receipt. Never treat an upload as a published post."""
    if not isinstance(response, dict) or response.get("error") or response.get("errors"):
        raise ContractRejected("provider response contained an error")
    data = response.get("data") if operation in {"media_upload", "create_post"} else response
    if not isinstance(data, dict):
        raise ContractRejected("missing provider receipt")
    value = data.get("id")
    return _id(value, f"{operation} receipt ID")


def require_container_finished(response: dict) -> None:
    if not isinstance(response, dict) or response.get("status_code") != "FINISHED":
        raise ContractRejected("Instagram container not ready for publishing")
