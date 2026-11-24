"""Immutable Facebook Daily Rates publication receipts, separate from quote audits.

This module has NO Facebook POST capability. It accepts a successful
independently verified publisher result and the original validated source
audit, and writes a new date-scoped receipt without modifying rate data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
PAGE_ID = "108130358772133"
BASE_PATH = Path("docs/daily-rates/facebook-publications")
RECEIPT_VERSION = 1
VERIFICATION = "META_PAGE_PHOTO_READBACK"
REASON = "Facebook Page photo independently verified"


class ReceiptRejected(ValueError):
    """An unverified, conflicting or unsafe receipt must never be persisted."""


def verified_receipt(
    provider_result: object, source_audit: object, *, source_commit: str,
    github_run_id: str, at_sast: datetime,
) -> dict:
    if not isinstance(provider_result, dict) or not isinstance(source_audit, dict):
        raise ReceiptRejected("missing provider result or source audit")
    if provider_result.get("status") != "PUBLISHED" or provider_result.get("reason") != REASON:
        raise ReceiptRejected("Facebook publication was not verified")
    if provider_result.get("page_id") != PAGE_ID:
        raise ReceiptRejected("Facebook Page identity mismatch")
    post_id = provider_result.get("provider_post_id")
    if not isinstance(post_id, str) or re.fullmatch(PAGE_ID + r"_[0-9]+", post_id) is None:
        raise ReceiptRejected("wrong Page post ID")
    date_sast = source_audit.get("date_sast")
    try:
        if not isinstance(date_sast, str) or datetime.strptime(date_sast, "%Y-%m-%d").date().isoformat() != date_sast:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ReceiptRejected("invalid source date") from exc
    if source_audit.get("status") != "VALIDATED":
        raise ReceiptRejected("original source audit not validated")
    if provider_result.get("reservation_tag") != "coinoswap-facebook-daily-rates-" + date_sast:
        raise ReceiptRejected("missing matching immutable date reservation")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ReceiptRejected("source commit must be immutable SHA-1")
    if not isinstance(github_run_id, str) or re.fullmatch(r"[0-9]{6,20}", github_run_id) is None:
        raise ReceiptRejected("GitHub publication run ID invalid")
    image = source_audit.get("image")
    if not isinstance(image, dict) or image.get("filename") != date_sast + ".png":
        raise ReceiptRejected("source image mismatch")
    digest = image.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ReceiptRejected("source checksum missing or invalid")
    link = provider_result.get("public_url")
    if not isinstance(link, str):
        raise ReceiptRejected("public Facebook permalink missing")
    u = urlsplit(link)
    if (u.scheme != "https" or u.hostname not in {"www.facebook.com", "facebook.com", "m.facebook.com"}
            or u.username is not None or u.password is not None or not u.path.strip("/")
            or u.fragment or u.port is not None):
        raise ReceiptRejected("public Facebook permalink invalid")
    if any(k.lower() in {"access_token", "token", "secret", "apikey", "api_key"}
           for k, v in parse_qsl(u.query, keep_blank_values=True)):
        raise ReceiptRejected("URL contains credential-like query keys")
    if not isinstance(at_sast, datetime) or at_sast.tzinfo is None or at_sast.utcoffset() is None:
        raise ReceiptRejected("timezone-aware publication timestamp required")
    stamp = at_sast.astimezone(SAST)
    if stamp.date().isoformat() != date_sast:
        raise ReceiptRejected("publication timestamp is for a different SAST date")
    try:
        target = datetime.fromisoformat(str(source_audit.get("target_sast")))
        if target.utcoffset() is None:
            raise ValueError()
        delta = (stamp - target.astimezone(SAST)).total_seconds()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReceiptRejected("invalid source publication target") from exc
    if not -5 <= delta <= 90:
        raise ReceiptRejected("publication receipt outside the target window")
    return {
        "receipt_version": RECEIPT_VERSION,
        "date_sast": date_sast,
        "platform": "facebook",
        "status": "PUBLISHED",
        "verification": VERIFICATION,
        "page_id": PAGE_ID,
        "provider_post_id": post_id,
        "public_url": link,
        "published_at_sast": stamp.isoformat(timespec="seconds"),
        "source_commit": source_commit,
        "source_image_sha256": digest,
        "reservation_tag": provider_result["reservation_tag"],
        "github_run_id": github_run_id,
        "github_run_url": f"https://github.com/Draztik99/coinoswap/actions/runs/{github_run_id}",
    }


def write_receipt(receipt: dict, *, root: Path = BASE_PATH) -> Path:
    day = receipt.get("date_sast")
    if receipt.get("status") != "PUBLISHED" or not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
        raise ReceiptRejected("only verified date-scoped publication receipts are supported")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (day + ".json")
    # Exclusive-create fails if another verified record already exists.
    try:
        with path.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, sort_keys=True, indent=2, ensure_ascii=False)
            output.write("\n")
    except FileExistsError as exc:
        raise ReceiptRejected("published receipt already exists; no overwrite") from exc
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist verified post receipt WITHOUT social API calls")
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--audit-json", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--github-run-id", required=True)
    args = parser.parse_args(argv)
    try:
        result_path, audit_path = Path(args.result_json), Path(args.audit_json)
        if not result_path.is_file() or result_path.stat().st_size > 16_000:
            raise ReceiptRejected("publisher result file absent or oversized")
        if not audit_path.is_file() or audit_path.stat().st_size > 256_000:
            raise ReceiptRejected("official source audit absent or oversized")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit_path.parent.as_posix() != "docs/daily-rates" or audit_path.name != audit.get("date_sast", "") + ".json":
            raise ReceiptRejected("not the official current-day source audit")
        receipt = verified_receipt(result, audit, source_commit=args.source_commit,
                                   github_run_id=args.github_run_id, at_sast=datetime.now(SAST))
        output = write_receipt(receipt)
    except (ReceiptRejected, OSError, ValueError, TypeError, UnicodeError):
        print("BLOCKED: independent, immutable Facebook receipt could not be recorded", file=sys.stderr)
        return 3  # A post may already be live; NEVER rerun publication.
    print(json.dumps({"status": "RECEIPT_RECORDED", "path": str(output), "post_id": receipt["provider_post_id"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
