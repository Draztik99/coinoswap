"""Read and validate official CoinoSwap Daily Rates artifacts. NO SOCIAL PUBLISHING.

The caller supplies a pinned 40-character main-branch commit SHA. Both files are
retrieved from the same immutable GitHub revision, not independently from main.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import struct
from dataclasses import dataclass
from datetime import date, datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
SUPPORTED = {"BTC": 1.0, "ETH": 1.0, "XMR": 2.0}
MAX_AUDIT_BYTES = 256_000
MAX_IMAGE_BYTES = 10_000_000
EXPECTED_SIZE = (1536, 1024)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class AssetRejected(ValueError):
    """Fail-closed validation: an asset must never be published."""


@dataclass(frozen=True)
class ValidatedAsset:
    date_sast: str
    target_sast: str
    image_sha256: str
    caption: str
    display_prices: dict[str, str]


def _time(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone missing")
        return parsed.astimezone(SAST)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AssetRejected(f"{field}: invalid timezone-aware timestamp") from exc


def _positive(value: object, field: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError("boolean")
        n = float(value)
        if not math.isfinite(n) or n <= 0:
            raise ValueError("non-positive/non-finite")
        return n
    except (TypeError, ValueError, OverflowError) as exc:
        raise AssetRejected(f"{field}: invalid positive price") from exc


def validate_asset_pair(audit_bytes: bytes, image_bytes: bytes, *, now: datetime) -> ValidatedAsset:
    """Validate both official artifacts for a publication opportunity at now.

    No network writes, social APIs or database mutations are possible here.
    Prices must still be current at the intended posting time.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise AssetRejected("now must be timezone-aware")
    now = now.astimezone(SAST)
    if len(audit_bytes) > MAX_AUDIT_BYTES or len(image_bytes) > MAX_IMAGE_BYTES:
        raise AssetRejected("asset exceeds maximum size")
    try:
        audit = json.loads(audit_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AssetRejected("audit is not valid UTF-8 JSON") from exc
    if not isinstance(audit, dict) or audit.get("status") != "VALIDATED":
        raise AssetRejected("audit not in VALIDATED state")
    today = now.date().isoformat()
    if audit.get("date_sast") != today:
        raise AssetRejected("SAST publication date does not match the asset")
    checked = _time(audit.get("checked_at_sast"), "checked_at_sast")
    if (checked - now).total_seconds() > 30:
        raise AssetRejected("audit validation time is in the future")
    target = _time(audit.get("target_sast"), "target_sast")
    if target.date() != now.date():
        raise AssetRejected("publication target date is not today")
    if (now - target).total_seconds() > 60:
        raise AssetRejected("publication target window expired")
    if (checked - target).total_seconds() > 0:
        raise AssetRejected("image was checked after publication target")

    image_meta = audit.get("image")
    if not isinstance(image_meta, dict):
        raise AssetRejected("image metadata missing")
    if image_meta.get("filename") != f"{today}.png":
        raise AssetRejected("unexpected image filename")
    digest = image_meta.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        raise AssetRejected("invalid image SHA-256 metadata")
    if not hmac.compare_digest(hashlib.sha256(image_bytes).hexdigest(), digest.lower()):
        raise AssetRejected("image SHA-256 mismatch")
    if len(image_bytes) < 33 or image_bytes[:8] != PNG_SIGNATURE or image_bytes[12:16] != b"IHDR":
        raise AssetRejected("image is not a PNG with IHDR")
    width, height = struct.unpack(">II", image_bytes[16:24])
    if (width, height) != EXPECTED_SIZE:
        raise AssetRejected("unexpected PNG dimensions")
    if image_meta.get("width") != width or image_meta.get("height") != height:
        raise AssetRejected("PNG dimensions differ from audit")

    coins = audit.get("coins")
    display = audit.get("display_prices")
    if not isinstance(coins, dict) or not isinstance(display, dict):
        raise AssetRejected("price data missing")
    if set(coins) != set(SUPPORTED) or set(display) != set(SUPPORTED):
        raise AssetRejected("wrong coin list")
    for sym, threshold in SUPPORTED.items():
        coin = coins[sym]
        if not isinstance(coin, dict):
            raise AssetRejected(f"{sym}: missing source data")
        a, b = coin.get("coinmarketcap"), coin.get("kraken")
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise AssetRejected(f"{sym}: both quote sources are required")
        cmc = _positive(a.get("usd"), f"{sym} CoinMarketCap")
        kraken = _positive(b.get("usd"), f"{sym} Kraken")
        displayed = _positive(coin.get("display_usd"), f"{sym} display")
        if abs(displayed - cmc) > 0.011:
            raise AssetRejected(f"{sym}: displayed USD value differs from CoinMarketCap")
        if display[sym] != "$" + f"{displayed:,.2f}":
            raise AssetRejected(f"{sym}: displayed price string mismatch")
        deviation = 100 * abs(cmc - kraken) / cmc
        if deviation > threshold:
            raise AssetRejected(f"{sym}: source price deviation too high")
        declared_threshold = _positive(coin.get("threshold_pct"), f"{sym} threshold")
        if declared_threshold > threshold or deviation > declared_threshold:
            raise AssetRejected(f"{sym}: audit threshold violation")
        for source_name, quote in (("CoinMarketCap", a), ("Kraken", b)):
            stamp = _time(quote.get("updated_sast"), f"{sym} {source_name}")
            age = (now - stamp).total_seconds()
            if not -30 <= age <= 300:
                raise AssetRejected(f"{sym}: {source_name} quote stale/future at posting")
    caption = audit.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        raise AssetRejected("caption missing")
    if len(caption) > 2000:
        raise AssetRejected("caption exceeds preflight maximum")
    return ValidatedAsset(
        date_sast=today,
        target_sast=target.isoformat(timespec="seconds"),
        image_sha256=digest.lower(),
        caption=caption.strip(),
        display_prices=dict(display),
    )


def fetch_pinned_pair(*, commit_sha: str, date_sast: str, recovery: bool = False) -> tuple[bytes, bytes]:
    """GET-only retrieval from an immutable GitHub commit (not floating main)."""
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha) is None:
        raise AssetRejected("a pinned 40-character commit SHA is required")
    try:
        if date.fromisoformat(date_sast).isoformat() != date_sast:
            raise ValueError("noncanonical date")
    except (TypeError, ValueError) as exc:
        raise AssetRejected("invalid SAST date") from exc
    if type(recovery) is not bool:
        raise AssetRejected("recovery selector must be boolean")
    source_dir = "docs/daily-rates/recovery" if recovery else "docs/daily-rates"
    base = (
        f"https://raw.githubusercontent.com/Draztik99/coinoswap/"
        f"{commit_sha}/{source_dir}/{date_sast}"
    )
    outputs = []
    for ext, max_bytes in (("json", MAX_AUDIT_BYTES), ("png", MAX_IMAGE_BYTES)):
        request = Request(base + "." + ext, headers={"User-Agent": "CoinoSwap-Shadow-Validator/1.0"})
        try:
            with urlopen(request, timeout=15) as response:
                payload = response.read(max_bytes + 1)
        except Exception as exc:
            raise AssetRejected(f"GitHub {ext} asset unavailable") from exc
        if len(payload) > max_bytes:
            raise AssetRejected(f"GitHub {ext} asset too large")
        outputs.append(payload)
    return outputs[0], outputs[1]
