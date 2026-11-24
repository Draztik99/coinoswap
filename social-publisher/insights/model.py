"""CoinoSwap Social Analytics v1: strict, provenance-first post records.

Pure data transformation. No Meta/Metricool requests and no publication actions.
Zero is a measured zero, None is unavailable, never interchangeable.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
PAGE_ID = "108130358772133"
METRICOOL_ID = "8283300"
FIELDS = ("reach","views","reactions","likes","comments","shares","saves","interactions","link_clicks")
IG_FIELDS = ("IGPO02","IGPO03","IGPO04","IGPO06","IGPO08","IGPO10",
             "IGPO12","IGPO13","IGPO14","IGPO15","IGPO27","IGPO28")


class AnalyticsError(ValueError):
    pass


def count(value, name: str):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalyticsError("invalid measured " + name)
    return value


def stamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AnalyticsError("timezone-aware collection time required")
    return value.astimezone(SAST).isoformat(timespec="seconds")


def safe_url(value: str, hosts: set[str]) -> str:
    if not isinstance(value, str):
        raise AnalyticsError("missing post URL")
    p = urlsplit(value)
    if (p.scheme != "https" or p.hostname not in hosts or p.username or p.password
            or p.fragment or not p.path.strip("/") or p.port is not None):
        raise AnalyticsError("invalid post URL")
    if any(x in p.query.lower() for x in ("access_token=", "token=", "api_key=", "secret=")):
        raise AnalyticsError("credential-bearing post URL")
    return value


def meta_count(container, label):
    """An omitted Graph summary is unavailable, not zero."""
    if not isinstance(container, dict) or not isinstance(container.get("summary"), dict):
        return None
    return count(container["summary"].get("total_count"), label)


def metric_values() -> dict:
    return {field: None for field in FIELDS}


def facebook_post_snapshot(post: dict, receipt: dict, *, collected_at: datetime,
                           media_insights: dict | None = None) -> dict:
    if not isinstance(post, dict) or not isinstance(receipt, dict):
        raise AnalyticsError("missing Meta post or verified receipt")
    if receipt.get("platform") != "facebook" or receipt.get("status") != "PUBLISHED":
        raise AnalyticsError("not a verified Facebook publication")
    pid = receipt.get("provider_post_id")
    if not isinstance(pid, str) or not pid.startswith(PAGE_ID + "_") or not pid[len(PAGE_ID)+1:].isdigit():
        raise AnalyticsError("invalid CoinoSwap Page post ID")
    if post.get("id") != pid or not isinstance(post.get("from"), dict) or post["from"].get("id") != PAGE_ID:
        raise AnalyticsError("Graph readback does not belong to CoinoSwap")
    date_sast = receipt.get("date_sast")
    if not isinstance(date_sast, str) or len(date_sast) != 10:
        raise AnalyticsError("receipt missing SAST publication date")
    published_at = receipt.get("published_at_sast")
    try:
        published = datetime.fromisoformat(published_at).astimezone(SAST)
    except (ValueError, TypeError, AttributeError) as exc:
        raise AnalyticsError("invalid verified publication time") from exc
    if published.date().isoformat() != date_sast:
        raise AnalyticsError("receipt date mismatch")
    url = safe_url(receipt.get("public_url"), {"facebook.com", "www.facebook.com", "m.facebook.com"})
    metrics = metric_values()
    metrics["reactions"] = meta_count(post.get("reactions"), "reactions")
    metrics["comments"] = meta_count(post.get("comments"), "comments")
    shares = post.get("shares")
    if isinstance(shares, dict):
        metrics["shares"] = count(shares.get("count"), "shares")
    if all(metrics[name] is not None for name in ("reactions", "comments", "shares")):
        metrics["interactions"] = sum(metrics[name] for name in ("reactions", "comments", "shares"))
    if media_insights is not None:
        if not isinstance(media_insights, dict) or not isinstance(media_insights.get("data"), list):
            raise AnalyticsError("invalid Meta Insights response")
        for item in media_insights["data"]:
            if not isinstance(item, dict) or item.get("name") != "post_media_view":
                continue
            values = item.get("values")
            if isinstance(values, list) and values and isinstance(values[0], dict):
                metrics["views"] = count(values[0].get("value"), "media views")
    return {
        "schema_version": 1, "platform": "facebook", "campaign_key": "daily_rates",
        "provider_post_id": pid, "date_sast": date_sast,
        "published_at_sast": published.isoformat(timespec="seconds"),
        "collected_at_sast": stamp(collected_at), "public_url": url,
        "source": "Meta Graph API v27.0 read-only post",
        "source_receipt": "docs/daily-rates/facebook-publications/" + date_sast + ".json",
        "metrics": metrics,
        "metric_status": "partial" if any(value is None for value in metrics.values()) else "complete",
    }


def instagram_metricool_row(row: object, *, collected_at: datetime) -> dict:
    """Metricool field IDs are mapped by an exact, versioned column order."""
    if not isinstance(row, list) or len(row) != len(IG_FIELDS):
        raise AnalyticsError("wrong Metricool Instagram field layout")
    mapping = dict(zip(IG_FIELDS, row))
    raw_stamp = mapping["IGPO02"]
    if not isinstance(raw_stamp, str) or len(raw_stamp) != 14 or not raw_stamp.isdigit():
        raise AnalyticsError("invalid Metricool post timestamp")
    try:
        published = datetime.strptime(raw_stamp, "%Y%m%d%H%M%S").replace(tzinfo=SAST)
    except ValueError as exc:
        raise AnalyticsError("invalid Metricool publication date") from exc
    caption = mapping["IGPO03"]
    if not isinstance(caption, str) or len(caption) > 10_000:
        raise AnalyticsError("invalid Instagram caption")
    pid = mapping["IGPO04"]
    if not isinstance(pid, str) or not pid.isdecimal() or len(pid) > 30:
        raise AnalyticsError("invalid Instagram post ID")
    url = safe_url(mapping["IGPO06"], {"instagram.com", "www.instagram.com"})
    def parse_int(field):
        x = mapping[field]
        if x is None or x == "":
            return None
        if not isinstance(x, str) or not x.isdecimal():
            raise AnalyticsError("invalid Metricool measurement: " + field)
        return count(int(x), field)
    metrics = metric_values()
    metrics["comments"] = parse_int("IGPO08")
    metrics["interactions"] = parse_int("IGPO12")
    metrics["likes"] = parse_int("IGPO13")
    metrics["reach"] = parse_int("IGPO14")
    metrics["saves"] = parse_int("IGPO15")
    metrics["shares"] = parse_int("IGPO27")
    metrics["views"] = parse_int("IGPO28")
    engagement = mapping["IGPO10"]
    if engagement is None or engagement == "":
        engagement_1000 = None
    else:
        try:
            engagement_1000 = float(engagement)
            if not (0 <= engagement_1000 < 1_000_000):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise AnalyticsError("invalid provider engagement per thousand") from exc
    return {
        "schema_version": 1, "platform": "instagram", "campaign_key": "daily_rates",
        "provider_post_id": pid, "date_sast": published.date().isoformat(),
        "published_at_sast": published.isoformat(timespec="seconds"),
        "collected_at_sast": stamp(collected_at), "public_url": url,
        "source": "Metricool IG feed posts; CoinoSwap brand timezone Africa/Johannesburg",
        "brand_id": METRICOOL_ID, "caption": caption,
        "metrics": metrics, "provider_engagement_per_1000": engagement_1000,
        "metric_status": "partial" if any(x is None for x in metrics.values()) else "complete",
    }
