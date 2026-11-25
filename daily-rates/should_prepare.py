"""CoinoSwap GitHub generator gate: safe retries inside selected SAST slot.

No network calls, social posts or price retrieval here. GitHub's scheduled
events can be delayed or dropped, so multiple cron candidates help but do
not guarantee execution. The price generator enforces stricter fresh quotes
and an image-completion cutoff independently.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from posting_slots import expected_prepare_time, slot_for_date

# Start a selected runner early enough to install dependencies BEFORE quote collection.
# Quotes are still retrieved only during the original 4-minute freshness window.
PREWARM_MINUTES = 15


class PreparationBlocked(ValueError):
    pass


def seconds_until_fresh_window(now: datetime) -> int:
    """Seconds until the original fresh-quote window; fail closed outside prewarm.

    This is a runner-timing helper, not permission to fetch stale prices.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise PreparationBlocked("SAST-aware clock required")
    now = now.astimezone(ZoneInfo("Africa/Johannesburg"))
    hour, minute = slot_for_date(now.date())
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    earliest = target - timedelta(minutes=PREWARM_MINUTES)
    cutoff = target - timedelta(minutes=1)
    if not earliest <= now < cutoff:
        raise PreparationBlocked("outside today's selected prewarm/cutoff window")
    prep_hour, prep_minute = expected_prepare_time(now.date())
    start = now.replace(hour=prep_hour, minute=prep_minute, second=0, microsecond=0)
    from math import ceil
    return max(0, ceil((start - now).total_seconds()))


def decide_preparation(
    now: datetime, *, emergency: bool = False,
    assets_dir: Path = Path("docs/daily-rates"),
) -> tuple[bool, str]:
    """Pure slot decision with idempotent, checksum-verified asset handling."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise PreparationBlocked("SAST-aware clock required")
    now = now.astimezone(ZoneInfo("Africa/Johannesburg"))
    chosen = slot_for_date(now.date())
    prep = expected_prepare_time(now.date())
    target_minutes = chosen[0] * 60 + chosen[1]
    now_minutes = now.hour * 60 + now.minute
    selected = emergency or (target_minutes - PREWARM_MINUTES <= now_minutes < target_minutes - 1)
    if not selected:
        return False, "outside selected preparation window"
    day = now.date().isoformat()
    assets_dir = Path(assets_dir)
    image = assets_dir / (day + ".png")
    manifest = assets_dir / (day + ".json")
    if not image.exists() and not manifest.exists():
        return True, "fresh asset not yet created"
    if not image.is_file() or not manifest.is_file():
        raise PreparationBlocked("incomplete daily asset pair; never overwrite")
    try:
        audit = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PreparationBlocked("existing manifest is unreadable") from exc
    meta = audit.get("image") if isinstance(audit, dict) else None
    if (
        not isinstance(meta, dict)
        or audit.get("status") != "VALIDATED"
        or audit.get("date_sast") != day
        or meta.get("filename") != image.name
    ):
        raise PreparationBlocked("existing manifest does not match today's validated image")
    declared = meta.get("sha256")
    if not isinstance(declared, str) or len(declared) != 64:
        raise PreparationBlocked("existing image checksum unavailable")
    try:
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
    except OSError as exc:
        raise PreparationBlocked("existing image cannot be checked") from exc
    if digest != declared.lower():
        raise PreparationBlocked("existing image checksum mismatch; never overwrite")
    return False, "already generated and checksum-verified: no duplicate"


def main() -> int:
    now = datetime.now(ZoneInfo("Africa/Johannesburg"))
    chosen = slot_for_date(now.date())
    prep = expected_prepare_time(now.date())
    emergency = os.environ.get("EMERGENCY_RATES", "").lower() == "true"
    try:
        selected, reason = decide_preparation(now, emergency=emergency)
    except PreparationBlocked as exc:
        print(f"FAIL CLOSED: {exc}", file=sys.stderr)
        return 2
    print(
        f"Today {now.date()}: selected publication {chosen[0]:02}:{chosen[1]:02} SAST; "
        f"prewarm up to {PREWARM_MINUTES} minutes ahead; fresh quotes start {prep[0]:02}:{prep[1]:02}, cutoff one minute before target. "
        f"Run at {now:%H:%M:%S} SAST. selected={selected}; reason={reason}"
    )
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write("selected=" + ("true" if selected else "false") + "\n")
            handle.write("reason=" + reason + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
