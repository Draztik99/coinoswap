"""Wait for a just-generated Daily Rates target, without sending posts.

Only a manual workflow invokes this. This step does not read secrets, request
Meta APIs, or change image artifacts. Exits nonzero if the posting window has
already been missed or if the local audit is invalid.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
MAX_WAIT_SECONDS = 240
MAX_AFTER_TARGET_SECONDS = 25


class WaitBlocked(ValueError):
    pass


def seconds_until_target(audit: object, *, now: datetime) -> int:
    if now.tzinfo is None or now.utcoffset() is None:
        raise WaitBlocked("timezone-aware SAST clock required")
    now = now.astimezone(SAST)
    if not isinstance(audit, dict) or audit.get("status") != "VALIDATED":
        raise WaitBlocked("current source has not been validated")
    if audit.get("date_sast") != now.date().isoformat():
        raise WaitBlocked("image is not for today's SAST date")
    try:
        target = datetime.fromisoformat(audit["target_sast"])
        checked = datetime.fromisoformat(audit["checked_at_sast"])
        if target.utcoffset() is None or checked.utcoffset() is None:
            raise ValueError("naive datetime")
        target = target.astimezone(SAST)
        checked = checked.astimezone(SAST)
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise WaitBlocked("image audit times invalid") from exc
    if target.date() != now.date() or checked.date() != now.date():
        raise WaitBlocked("cross-day target is not allowed")
    if not 0 <= (target - checked).total_seconds() <= 300:
        raise WaitBlocked("image preparation timing invalid")
    remaining = (target - now).total_seconds()
    if remaining > MAX_WAIT_SECONDS or remaining < -MAX_AFTER_TARGET_SECONDS:
        raise WaitBlocked("posting window is unavailable or has expired")
    return max(0, math.ceil(remaining))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait for fresh official SAST rates target")
    parser.add_argument("--audit", required=True, help="Local daily-rates JSON manifest")
    args = parser.parse_args(argv)
    path = Path(args.audit)
    try:
        day = datetime.now(SAST).date().isoformat()
        if path.name != day + ".json" or path.parent.as_posix() != "docs/daily-rates":
            raise WaitBlocked("only today's official Daily Rates manifest allowed")
        if not path.is_file() or path.stat().st_size > 256_000:
            raise WaitBlocked("today's local rates audit missing or oversized")
        audit = json.loads(path.read_text(encoding="utf-8"))
        wait = seconds_until_target(audit, now=datetime.now(SAST))
        print("Validated asset available. Waiting for SAST publication target; no post created.",
              flush=True)
        if wait:
            time.sleep(wait)
        seconds_until_target(audit, now=datetime.now(SAST))
    except (WaitBlocked, OSError, ValueError, TypeError, UnicodeError):
        print("BLOCKED: invalid or expired fresh-price publication target", file=sys.stderr)
        return 2
    print("Publication target is now open. Next step must independently validate price freshness.",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
