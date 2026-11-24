"""Read-only Meta Graph post analytics collector for verified CoinoSwap receipts.

Only fixed GET endpoints are contacted; all outputs are aggregate public-post
counts and metadata. No social POST, token persistence or URL redirects.
Nonavailable Meta insights are recorded as null, not silently set to zero.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facebook_health import GRAPH_ME_URL, _safe_token, _RejectRedirects
from facebook_page_auth import confirm_page_token_identity
from contracts import ContractRejected, META_API_VERSION
from model import SAST, PAGE_ID, AnalyticsError, facebook_post_snapshot

RECEIPT_DIR = Path("docs/daily-rates/facebook-publications")
OUTPUT_DIR = Path("docs/social-analytics/snapshots/facebook")
MAX_BYTES = 64_000
TOKEN_ENV = "COINOSWAP_FB_PAGE_ACCESS_TOKEN"
POST_FIELDS = "id,from{id},created_time,permalink_url,reactions.limit(0).summary(true),comments.limit(0).summary(true),shares"
METRIC = "post_media_view"
MAX_AGE_DAYS = 32


class CollectorUnavailable(RuntimeError):
    pass


def graph_get(opener, *, url: str, token: str, allowlist: set[str]) -> dict:
    if url not in allowlist or not url.startswith("https://graph.facebook.com/"):
        raise CollectorUnavailable("unapproved Meta read endpoint")
    request = Request(url, method="GET", headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "User-Agent": "CoinoSwap-ReadOnly-Analytics/1.0",
    })
    with opener.open(request, timeout=12) as response:
        if getattr(response, "status", 200) != 200:
            raise CollectorUnavailable("Meta GET returned non-success")
        blob = response.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES:
        raise CollectorUnavailable("Meta response exceeds limit")
    data = json.loads(blob.decode("utf-8"))
    if not isinstance(data, dict) or data.get("error"):
        raise CollectorUnavailable("Meta GET data invalid")
    return data


def _receipt(path: Path, *, now: datetime) -> dict | None:
    """Reject any invalid record rather than trusting a guessed publication."""
    if not re.fullmatch(r"20\d\d-\d\d-\d\d\.json", path.name):
        return None
    if path.stat().st_size > 32_000:
        raise CollectorUnavailable("receipt too large")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        day = datetime.strptime(path.stem, "%Y-%m-%d").date()
    except (OSError, ValueError, TypeError) as exc:
        raise CollectorUnavailable("unreadable verified publication receipt") from exc
    if (not isinstance(obj, dict) or obj.get("date_sast") != path.stem or
            obj.get("platform") != "facebook" or obj.get("status") != "PUBLISHED" or
            obj.get("verification") != "META_PAGE_PHOTO_READBACK" or
            obj.get("page_id") != PAGE_ID):
        raise CollectorUnavailable("unexpected Facebook receipt identity")
    pid = obj.get("provider_post_id")
    if not isinstance(pid, str) or re.fullmatch(PAGE_ID + r"_[0-9]+", pid) is None:
        raise CollectorUnavailable("invalid verified Page post ID")
    today = now.astimezone(SAST).date()
    if day > today or (today - day).days > MAX_AGE_DAYS:
        return None
    return obj


def collect(*, token: str, now: datetime, root: Path = RECEIPT_DIR,
            output: Path = OUTPUT_DIR, opener=None) -> dict:
    if not _safe_token(token):
        raise CollectorUnavailable("Meta analytics token unavailable or invalid")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise CollectorUnavailable("collection requires a timezone-aware clock")
    now = now.astimezone(SAST)
    if opener is None:
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                              _RejectRedirects())
    try:
        meta = graph_get(opener, url=GRAPH_ME_URL, token=token, allowlist={GRAPH_ME_URL})
        confirm_page_token_identity(meta)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError,
            ContractRejected, UnicodeError, json.JSONDecodeError) as exc:
        raise CollectorUnavailable("CoinoSwap Meta Page authentication failed") from None
    if not root.is_dir():
        return {"status":"NO_VERIFIED_RECEIPTS","snapshots_created":0,"posts_eligible":0}
    prepared = []
    for path in sorted(root.glob("*.json")):
        receipt = _receipt(path, now=now)
        if receipt is None:
            continue
        destination = output / receipt["date_sast"] / (now.date().isoformat()+".json")
        if destination.exists():
            # A day's snapshot is immutable; re-running must never change it.
            continue
        pid = receipt["provider_post_id"]
        url = f"https://graph.facebook.com/{META_API_VERSION}/{pid}?" + urlencode({"fields":POST_FIELDS})
        insight_url = f"https://graph.facebook.com/{META_API_VERSION}/{pid}/insights?" + urlencode({"metric":METRIC})
        try:
            post = graph_get(opener, url=url, token=token, allowlist={url})
        except (HTTPError, URLError, OSError, TimeoutError, ValueError,
                UnicodeError, json.JSONDecodeError, CollectorUnavailable):
            # Fail: claiming an analytics snapshot without validating the post
            # would misrepresent its provenance.
            raise CollectorUnavailable("Meta post readback failed; no analytics committed") from None
        insights = None
        try:
            insights = graph_get(opener, url=insight_url, token=token, allowlist={insight_url})
        except (HTTPError, URLError, OSError, TimeoutError, ValueError,
                UnicodeError, json.JSONDecodeError, CollectorUnavailable):
            # Optional metric may be deprecated or denied; leave views=N/A.
            pass
        try:
            snap = facebook_post_snapshot(post, receipt, collected_at=now, media_insights=insights)
        except AnalyticsError:
            raise CollectorUnavailable("provider metrics failed provenance validation") from None
        prepared.append((destination, snap))
    # Validate ALL responses before writing ANY snapshot to disk.
    for dest, snapshot in prepared:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with dest.open("x", encoding="utf-8") as handle:
                json.dump(snapshot, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
        except FileExistsError:
            raise CollectorUnavailable("immutable daily analytics snapshot already exists") from None
    return {"status":"COLLECTED","snapshots_created":len(prepared),
            "posts_eligible":len(prepared)}


def main() -> int:
    try:
        result = collect(token=os.getenv(TOKEN_ENV,""), now=datetime.now(SAST))
        print(json.dumps(result, sort_keys=True))
        return 0
    except CollectorUnavailable as exc:
        # Never print a raw provider error, response body, or API credentials.
        print(json.dumps({"status":"COLLECTION_BLOCKED","reason":str(exc),
                          "social_posts_created":0}),file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
