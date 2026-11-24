"""Read-only CoinoSwap social publisher preflight.

There is deliberately NO X API, Meta API, token handling, send function, or
publishing flag in this program. It cannot create a social post.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from asset_reader import SAST, AssetRejected, fetch_pinned_pair, validate_asset_pair


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run only: NEVER publishes")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--audit", help="Existing official JSON audit, local read-only")
    inputs.add_argument("--commit-sha", help="Pinned main-branch SHA for read-only GitHub GET")
    parser.add_argument("--image", help="PNG pair required with --audit")
    parser.add_argument("--at-sast", help="Local fixture testing only, ISO datetime with offset")
    args = parser.parse_args(argv)
    if bool(args.audit) != bool(args.image):
        parser.error("--audit and --image must be supplied together")
    if args.commit_sha and args.at_sast:
        parser.error("--at-sast is only allowed for local fixture testing")
    now = datetime.now(SAST)
    if args.at_sast:
        try:
            parsed = datetime.fromisoformat(args.at_sast)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("timezone offset required")
            now = parsed.astimezone(SAST)
        except (TypeError, ValueError) as exc:
            parser.error(f"invalid --at-sast: {exc}")
    try:
        if args.audit:
            audit = Path(args.audit).read_bytes()
            image = Path(args.image).read_bytes()
        else:
            audit, image = fetch_pinned_pair(
                commit_sha=args.commit_sha,
                date_sast=now.date().isoformat(),
            )
        asset = validate_asset_pair(audit, image, now=now)
    except (AssetRejected, OSError) as exc:
        print(json.dumps({
            "mode": "DRY_RUN_NO_SOCIAL_WRITES",
            "result": "BLOCKED",
            "reason": str(exc),
            "social_posts_created": 0,
        }))
        return 2

    print(json.dumps({
        "mode": "DRY_RUN_NO_SOCIAL_WRITES",
        "result": "VALIDATED_PREVIEW_ONLY",
        "date_sast": asset.date_sast,
        "target_sast": asset.target_sast,
        "image_sha256": asset.image_sha256,
        "caption": asset.caption,
        "display_prices": asset.display_prices,
        "platforms": {
            platform: "WOULD_PREPARE_ONLY"
            for platform in ("x", "facebook", "instagram")
        },
        "social_posts_created": 0,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
