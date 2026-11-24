"""Manual Facebook publisher entrypoint: default is a zero-network BLOCK.

A real send requires an explicit GitHub Actions main-branch manual workflow,
a separate protected environment, live flag, explicit cutover flag and a
private Page token. No scheduler, imports or tests can trigger publication.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from asset_reader import SAST, AssetRejected, fetch_pinned_pair, validate_asset_pair
from facebook_once import publish_once, APPROVAL_PHRASE
from tag_ledger import TagReservation

TOKEN_ENV = "COINOSWAP_FB_PAGE_ACCESS_TOKEN"


def _result(status: str, reason: str) -> int:
    print(json.dumps({"status": status, "reason": reason, "published_posts_created": 0},
                     sort_keys=True))
    return 2


def main(argv: list[str] | None = None, *, env=None) -> int:
    parser = argparse.ArgumentParser(description="Explicit manual Facebook-only post, never automatic")
    parser.add_argument("--publish", action="store_true", help="Send only if all approvals hold")
    parser.add_argument("--commit-sha", help="Immutable production GitHub commit")
    args = parser.parse_args(argv)
    if not args.publish:
        return _result("BLOCKED", "default is no-post: explicit manual --publish required")
    env = os.environ if env is None else env
    if env.get("GITHUB_REF") != "refs/heads/main" or env.get("GITHUB_REPOSITORY") != "Draztik99/coinoswap":
        return _result("BLOCKED", "only main-branch GitHub runner may request publication")
    if env.get("APPROVAL_PHRASE") != APPROVAL_PHRASE:
        return _result("BLOCKED", "manual single-post approval not supplied")
    if (env.get("COINOSWAP_FB_LIVE_ENABLED") != "true"
            or env.get("COINOSWAP_METRICOOL_FB_DISABLED") != "confirmed"):
        return _result("BLOCKED", "manual launch and Metricool Facebook cutover flags missing")
    if not isinstance(args.commit_sha, str) or re.fullmatch(r"[0-9a-fA-F]{40}", args.commit_sha) is None:
        return _result("BLOCKED", "immutable production commit not supplied")
    token = env.get(TOKEN_ENV)
    if not isinstance(token, str) or not token or len(token) > 4096:
        return _result("BLOCKED", "private Page token not configured")
    now = datetime.now(SAST)
    try:
        manifest, image = fetch_pinned_pair(
            commit_sha=args.commit_sha, date_sast=now.date().isoformat())
        asset = validate_asset_pair(manifest, image, now=now)
    except (AssetRejected, OSError):
        return _result("BLOCKED", "official current-day image validation failed")
    result = publish_once(
        asset, pinned_commit=args.commit_sha, token=token, environ=env,
        approval_phrase=env["APPROVAL_PHRASE"],
        reservation=TagReservation(Path.cwd()),
    )
    print(json.dumps(asdict(result), sort_keys=True))
    if result.status == "PUBLISHED":
        return 0
    if result.status == "UNKNOWN":
        return 3
    return 2


if __name__ == "__main__":
    sys.exit(main())
