"""Facebook-only SHADOW preview. Cannot create, schedule or send social posts.

Reads only a pinned GitHub asset pair, validates with existing source rules,
and builds an inert Meta POST request description. The request is never executed.
Live publication remains blocked while Metricool is the active publisher.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

from asset_reader import SAST, AssetRejected, ValidatedAsset, fetch_pinned_pair, validate_asset_pair
from contracts import ContractRejected, facebook_page_photo
from facebook_page_auth import COINOSWAP_PAGE_ID
from launch_gate import evaluate_release_gate

CAMPAIGN_KEY = "daily_rates"
PINNED_RE = re.compile(r"[0-9a-fA-F]{40}")


@dataclass(frozen=True)
class FacebookShadowPreview:
    status: str
    reason: str
    page_id: str
    date_sast: str
    campaign_key: str
    image_sha256: str
    validated_image_url: str
    intended_api_operation: str
    published_posts_created: int = 0


def build_facebook_shadow_preview(
    asset: ValidatedAsset, *, pinned_main_commit: str, metricool_active: bool = True
) -> FacebookShadowPreview:
    """Build a publication-shaped preview from a validated official asset only.

    Even if metricool_active is false, this code has no HTTP POST transport and
    cannot authorize publication. Do not mistake a preview for a live receipt.
    """
    if not isinstance(asset, ValidatedAsset):
        raise AssetRejected("official validated asset required")
    if not isinstance(pinned_main_commit, str) or PINNED_RE.fullmatch(pinned_main_commit) is None:
        raise AssetRejected("immutable main commit SHA required")
    if re.fullmatch(r"[0-9a-fA-F]{64}", asset.image_sha256) is None:
        raise AssetRejected("invalid validated image digest")
    if not isinstance(asset.date_sast, str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", asset.date_sast):
        raise AssetRejected("invalid validated SAST date")
    if asset.target_sast[:10] != asset.date_sast:
        raise AssetRejected("asset target date mismatch")
    if metricool_active is not True and metricool_active is not False:
        raise AssetRejected("Metricool status must be explicit")
    image_url = (
        "https://raw.githubusercontent.com/Draztik99/coinoswap/"
        + pinned_main_commit + "/docs/daily-rates/" + asset.date_sast + ".png"
    )
    # This builds a data-only RequestSpec, with no HTTP transport or tokens.
    request = facebook_page_photo(COINOSWAP_PAGE_ID, asset.caption, image_url)
    if request.method != "POST" or request.operation != "page_photo":
        raise ContractRejected("unexpected inert Facebook photo contract")
    guard = evaluate_release_gate("facebook", metricool_active=metricool_active)
    if guard.ready_for_further_live_integration:
        raise ContractRejected("shadow preview unexpectedly authorized publication")
    return FacebookShadowPreview(
        status="BLOCKED_METRICOOL" if metricool_active else "SHADOW_ONLY",
        reason="Metricool remains active for Facebook" if metricool_active else guard.reason,
        page_id=COINOSWAP_PAGE_ID,
        date_sast=asset.date_sast,
        campaign_key=CAMPAIGN_KEY,
        image_sha256=asset.image_sha256,
        validated_image_url=image_url,
        intended_api_operation=request.operation,
    )


def preview_pinned_asset(
    *, pinned_main_commit: str, at_sast: datetime | None = None
) -> FacebookShadowPreview:
    """GET official audit/PNG at one pinned commit; validate before preview."""
    now = datetime.now(SAST) if at_sast is None else at_sast
    if now.tzinfo is None or now.utcoffset() is None:
        raise AssetRejected("time must have an explicit timezone")
    now = now.astimezone(SAST)
    audit, png = fetch_pinned_pair(
        commit_sha=pinned_main_commit, date_sast=now.date().isoformat()
    )
    asset = validate_asset_pair(audit, png, now=now)
    return build_facebook_shadow_preview(asset, pinned_main_commit=pinned_main_commit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoinoSwap Facebook SHADOW only: 0 posts")
    parser.add_argument("--commit-sha", required=True, help="Pinned immutable main commit")
    args = parser.parse_args(argv)
    try:
        preview = preview_pinned_asset(pinned_main_commit=args.commit_sha)
    except (AssetRejected, ContractRejected, OSError) as exc:
        print(json.dumps({
            "mode": "FACEBOOK_SHADOW_ZERO_POSTS", "status": "BLOCKED_VALIDATION",
            "reason": str(exc), "published_posts_created": 0,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "mode": "FACEBOOK_SHADOW_ZERO_POSTS", **asdict(preview),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
