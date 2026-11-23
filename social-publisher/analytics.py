"""Pure offline analytics normalization and attribution validation.

This module never claims impressions, website visits or completed swaps that
were not provided by a verified upstream event source.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

PLATFORMS = ("x", "facebook", "instagram")
BASE_URL = "https://www.coinoswap.com/"


class AnalyticsRejected(ValueError):
    pass


def tracked_url(platform: str, date_sast: str, *, campaign: str = "daily_rates") -> str:
    if platform not in PLATFORMS:
        raise AnalyticsRejected("invalid platform")
    from datetime import date
    try:
        if date.fromisoformat(date_sast).isoformat() != date_sast:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise AnalyticsRejected("invalid date") from exc
    if campaign != "daily_rates":
        raise AnalyticsRejected("campaign not approved")
    parts = urlsplit(BASE_URL)
    query = dict(parse_qsl(parts.query))
    query.update({
        "utm_source": platform,
        "utm_medium": "organic_social",
        "utm_campaign": campaign,
        "utm_content": date_sast,
    })
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def normalize_metrics(platform: str, provider_record: dict) -> dict:
    """Accept only explicitly measured counts, preserving absent values as None."""
    if platform not in PLATFORMS or not isinstance(provider_record, dict):
        raise AnalyticsRejected("invalid provider metrics")
    allowed = ("impressions", "views", "likes", "comments", "shares", "reposts", "link_clicks")
    result = {"platform": platform, "metric_source": provider_record.get("metric_source")}
    if not isinstance(result["metric_source"], str) or not result["metric_source"].strip():
        raise AnalyticsRejected("metric provenance missing")
    for name in allowed:
        raw = provider_record.get(name)
        if raw is None:
            result[name] = None
        elif isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise AnalyticsRejected(f"invalid {name}")
        else:
            result[name] = raw
    if platform == "instagram" and result["link_clicks"] is not None:
        # Per-post website clicks cannot be inferred from profile visits.
        raise AnalyticsRejected("per-post Instagram outbound clicks not verified")
    numerator = [result[name] for name in ("likes", "comments", "shares", "reposts")]
    denom = result["impressions"] if result["impressions"] is not None else result["views"]
    result["engagement_rate"] = (
        (sum(numerator) / denom) if denom and all(n is not None for n in numerator) else None
    )
    return result


def confirmed_swap_funnel(sessions: list[dict], swaps: list[dict]) -> dict:
    """Exact session->completion matching only; no probabilistic attribution."""
    if not isinstance(sessions,list) or not isinstance(swaps,list):
        raise AnalyticsRejected("sessions and swaps must be lists")
    tracked = {}
    for session in sessions:
        if not isinstance(session,dict):
            raise AnalyticsRejected("malformed session")
        sid = session.get("session_id")
        platform = session.get("utm_source")
        if not isinstance(sid,str) or not sid:
            raise AnalyticsRejected("missing session identifier")
        if sid in tracked:
            continue  # deduplicate repeated website event for same session
        tracked[sid] = platform if platform in PLATFORMS else None

    completed = {}
    for event in swaps:
        if not isinstance(event,dict):
            raise AnalyticsRejected("malformed swap")
        if event.get("status") != "completed" or event.get("verified") is not True:
            continue
        tx = event.get("swap_id")
        if not isinstance(tx,str) or not tx:
            raise AnalyticsRejected("verified swap missing unique id")
        try:
            volume = Decimal(str(event.get("volume_usd")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise AnalyticsRejected("invalid swap USD volume") from exc
        if not volume.is_finite() or volume < 0:
            raise AnalyticsRejected("negative/nonfinite swap volume")
        if tx in completed:
            if completed[tx][0] != volume:
                raise AnalyticsRejected("conflicting duplicate swap volume")
            continue
        completed[tx] = (volume, event.get("session_id"))

    by_source = defaultdict(lambda: {"visits": 0, "completed_swaps": 0, "volume_usd": Decimal(0)})
    for platform in tracked.values():
        if platform:
            by_source[platform]["visits"] += 1
    total_volume = Decimal(0)
    attributed = 0
    for volume, sid in completed.values():
        total_volume += volume
        platform = tracked.get(sid) if isinstance(sid,str) else None
        if platform:
            by_source[platform]["completed_swaps"] += 1
            by_source[platform]["volume_usd"] += volume
            attributed += 1
    return {
        "tracked_sessions": len(tracked),
        "verified_completed_swaps": len(completed),
        "completed_volume_usd": str(total_volume),
        "attributed_completed_swaps": attributed,
        "unattributed_completed_swaps": len(completed)-attributed,
        "by_platform": {
            p: {
                "tracked_visits": by_source[p]["visits"],
                "attributed_completed_swaps": by_source[p]["completed_swaps"],
                "attributed_volume_usd": str(by_source[p]["volume_usd"]),
            }
            for p in PLATFORMS
        },
    }
