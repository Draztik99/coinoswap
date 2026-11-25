"""Wait in a pre-warmed runner until the strict fresh-price preparation window.

This step cannot fetch prices, post to social networks, or authorize stale quotes.
The generator independently enforces the original quote-freshness and image cutoff.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from should_prepare import PreparationBlocked, seconds_until_fresh_window

SAST = ZoneInfo("Africa/Johannesburg")


def main() -> int:
    try:
        wait = seconds_until_fresh_window(datetime.now(SAST))
        if wait:
            print(
                f"Pre-warmed runner ready; holding {wait}s until fresh-price window.",
                flush=True,
            )
            time.sleep(wait)
        # Recheck the actual current clock and fail closed if the window expired.
        if seconds_until_fresh_window(datetime.now(SAST)):
            raise PreparationBlocked("runner woke before freshness window")
    except PreparationBlocked as exc:
        print("FAIL CLOSED: freshness preparation timing unavailable: " + str(exc),
              file=sys.stderr)
        return 2
    print("Fresh-price preparation window open (no social post).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
