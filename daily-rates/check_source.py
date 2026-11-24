"""Read-only Daily Rates source readiness audit; never schedules or publishes.

Checks the official source image and JSON once every eligible day. This job is
an operational alarm only: a present image does NOT mean a social post exists.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class SourceMissing(RuntimeError):
    pass


def audit_source(*, date_sast: str, directory: Path) -> dict:
    if not isinstance(date_sast, str) or len(date_sast) != 10:
        raise SourceMissing("invalid SAST date")
    try:
        canonical = datetime.strptime(date_sast, "%Y-%m-%d").date().isoformat()
    except (ValueError, TypeError) as exc:
        raise SourceMissing("invalid SAST date") from exc
    if canonical != date_sast:
        raise SourceMissing("noncanonical SAST date")
    directory = Path(directory)
    json_file = directory / (date_sast + ".json")
    png_file = directory / (date_sast + ".png")
    if not json_file.is_file() or not png_file.is_file():
        raise SourceMissing("validated current-day image or manifest absent")
    if json_file.stat().st_size > 256_000 or png_file.stat().st_size > 10_000_000:
        raise SourceMissing("source asset exceeds size limit")
    try:
        audit = json.loads(json_file.read_text(encoding="utf-8"))
        png = png_file.read_bytes()
    except (OSError, ValueError, UnicodeError) as exc:
        raise SourceMissing("source asset unreadable") from exc
    if not isinstance(audit, dict) or audit.get("status") != "VALIDATED":
        raise SourceMissing("source manifest is not validated")
    if audit.get("date_sast") != date_sast:
        raise SourceMissing("source manifest date mismatch")
    meta = audit.get("image")
    if not isinstance(meta, dict) or meta.get("filename") != png_file.name:
        raise SourceMissing("manifest image filename mismatch")
    sha = meta.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or hashlib.sha256(png).hexdigest() != sha.lower():
        raise SourceMissing("manifest PNG checksum mismatch")
    if len(png) < 33 or not png.startswith(b"\x89PNG\r\n\x1a\n") or png[12:16] != b"IHDR":
        raise SourceMissing("invalid PNG header")
    dimensions = struct.unpack(">II", png[16:24])
    if dimensions != (1536, 1024) or meta.get("width") != 1536 or meta.get("height") != 1024:
        raise SourceMissing("unexpected source image dimensions")
    timestamps = []
    for name in ("checked_at_sast", "target_sast"):
        try:
            stamp = datetime.fromisoformat(str(audit.get(name)))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("timezone")
            timestamps.append(stamp.astimezone(ZoneInfo("Africa/Johannesburg")))
        except (ValueError, TypeError, OverflowError) as exc:
            raise SourceMissing(f"invalid {name} timestamp") from exc
    checked, target = timestamps
    if checked.date().isoformat() != date_sast or target.date().isoformat() != date_sast:
        raise SourceMissing("source timestamp is for a different SAST date")
    if not 0 <= (target - checked).total_seconds() <= 300:
        raise SourceMissing("image audit timing outside expected window")
    return {"date_sast": date_sast, "status": "VALIDATED_SOURCE_PRESENT",
            "target_sast": target.isoformat(timespec="seconds"),
            "sha256": sha.lower(), "social_posts_created": 0}


def main() -> int:
    today = datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat()
    try:
        result = audit_source(date_sast=today, directory=Path("docs/daily-rates"))
    except SourceMissing as exc:
        print("SOURCE GENERATION MISSING — DO NOT PUBLISH:", str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
