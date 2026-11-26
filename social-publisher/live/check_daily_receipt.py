"""Read-only daily direct Facebook publication receipt alarm (NO POST).

Exit nonzero when the selected SAST day lacks a verified Facebook receipt.
Does not assume green generator workflow means a published social post.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
PAGE = "108130358772133"
SOURCE = Path("docs/daily-rates")

class MissingVerifiedPublication(ValueError):
    pass

def inspect(day: str, root: Path = SOURCE) -> dict:
    try:
        if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
            raise ValueError("day")
    except (ValueError, TypeError) as exc:
        raise MissingVerifiedPublication("INVALID_DAY") from exc
    root=Path(root)
    receipt=root/"facebook-publications"/(day+".json")
    if not receipt.is_file():
        raise MissingVerifiedPublication("FACEBOOK_RECEIPT_MISSING")
    try:
        if receipt.stat().st_size > 32_000:
            raise MissingVerifiedPublication("OVERSIZED_RECORD")
        posted=json.loads(receipt.read_text(encoding="utf-8"))
        if not isinstance(posted,dict):
            raise MissingVerifiedPublication("INVALID_RECORD")
        # The source is either the official daily pair or an explicitly verified
        # same-day recovery pair. Never follow an arbitrary receipt file path.
        official="docs/daily-rates/"+day+".json"
        recovery="docs/daily-rates/recovery/"+day+".json"
        source_path=posted.get("source_asset_path",official)
        if source_path not in {official,recovery}:
            raise MissingVerifiedPublication("SOURCE_PATH_INVALID")
        folder=root/("recovery" if source_path==recovery else "")
        manifest=folder/(day+".json")
        image=folder/(day+".png")
        if not manifest.is_file() or not image.is_file():
            raise MissingVerifiedPublication("SOURCE_MISSING")
        if manifest.stat().st_size > 256_000 or image.stat().st_size > 10_000_000:
            raise MissingVerifiedPublication("OVERSIZED_RECORD")
        source=json.loads(manifest.read_text(encoding="utf-8"))
        digest=hashlib.sha256(image.read_bytes()).hexdigest()
    except (OSError,UnicodeError,ValueError,TypeError) as exc:
        raise MissingVerifiedPublication("INVALID_RECORD") from exc
    if (not isinstance(source,dict) or source.get("status")!="VALIDATED"
            or source.get("date_sast")!=day
            or not isinstance(source.get("image"),dict)
            or source["image"].get("filename")!=day+".png"
            or source["image"].get("sha256")!=digest):
        raise MissingVerifiedPublication("SOURCE_INTEGRITY_FAILED")
    if (not isinstance(posted,dict) or posted.get("date_sast")!=day
            or posted.get("platform")!="facebook"
            or posted.get("status")!="PUBLISHED"
            or posted.get("verification")!="META_PAGE_PHOTO_READBACK"
            or posted.get("page_id")!=PAGE
            or posted.get("reservation_tag")!="coinoswap-facebook-daily-rates-"+day
            or posted.get("source_image_sha256")!=digest):
        raise MissingVerifiedPublication("FACEBOOK_RECEIPT_MISMATCH")
    post=posted.get("provider_post_id")
    if not isinstance(post,str) or re.fullmatch(re.escape(PAGE)+r"_[0-9]+",post) is None:
        raise MissingVerifiedPublication("FACEBOOK_POST_ID_INVALID")
    link=posted.get("public_url")
    if not isinstance(link,str):
        raise MissingVerifiedPublication("FACEBOOK_PERMALINK_INVALID")
    url=urlsplit(link)
    if (url.scheme!="https" or url.hostname not in
            {"facebook.com","www.facebook.com","m.facebook.com"}
            or url.username or url.password or url.fragment or not url.path.strip("/")):
        raise MissingVerifiedPublication("FACEBOOK_PERMALINK_INVALID")
    sha=posted.get("source_commit")
    if not isinstance(sha,str) or re.fullmatch("[0-9a-f]{40}",sha) is None:
        raise MissingVerifiedPublication("SOURCE_COMMIT_INVALID")
    return {"date_sast":day,"platform":"facebook","status":"VERIFIED_PUBLICATION_RECEIPT",
            "provider_post_id":post,"public_url":link}

def main() -> int:
    day=datetime.now(SAST).date().isoformat()
    try:
        result=inspect(day)
    except MissingVerifiedPublication as exc:
        print("FACEBOOK_DAILY_RATES_ALERT: "+str(exc)+" for "+day, file=sys.stderr)
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
