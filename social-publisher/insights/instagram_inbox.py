"""Convert approved Metricool connector inbox files to immutable IG snapshots.

This module makes NO network requests and never posts to any social platform.
Inbox items are created separately by the existing read-only Metricool connector.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from model import AnalyticsError, IG_FIELDS, METRICOOL_ID, SAST
from instagram_import import convert, save

INBOX=Path("docs/social-analytics/inbox/instagram")
OUTPUT=Path("docs/social-analytics/snapshots/instagram")


def validate_inbox(payload: object, filename: str) -> tuple[dict,datetime]:
    if not isinstance(payload,dict) or payload.get("schema_version")!=1:
        raise AnalyticsError("Metricool inbox schema unrecognized")
    if payload.get("brand_id")!=METRICOOL_ID:
        raise AnalyticsError("wrong Metricool brand")
    if payload.get("metric_field_ids")!=list(IG_FIELDS):
        raise AnalyticsError("Metricool field layout changed")
    if not re.fullmatch(r"20\d\d-\d\d-\d\d\.json",filename):
        raise AnalyticsError("invalid dated Metricool inbox file")
    try:
        collected=datetime.fromisoformat(payload["retrieved_at_sast"])
        if collected.tzinfo is None or collected.utcoffset() is None:
            raise ValueError()
        collected=collected.astimezone(SAST)
    except (KeyError,ValueError,TypeError) as exc:
        raise AnalyticsError("Metricool extraction timestamp unavailable") from exc
    if filename!=collected.date().isoformat()+".json":
        raise AnalyticsError("Metricool inbox date mismatch")
    if not isinstance(payload.get("rows"),list):
        raise AnalyticsError("Metricool rows are missing")
    return {"rows":payload["rows"]}, collected


def process_inbox(*, inbox=INBOX,output=OUTPUT) -> dict:
    inbox,output=Path(inbox),Path(output)
    if not inbox.is_dir():
        return {"status":"NO_INBOX","imported":0,"skipped_existing":0}
    prepared=[]
    skipped=0
    for source in sorted(inbox.glob("*.json")):
        if source.stat().st_size>512_000:
            raise AnalyticsError("Metricool inbox exceeds size limit")
        dest=output/source.name
        if dest.exists():
            skipped+=1
            continue
        try:
            payload=json.loads(source.read_text(encoding="utf-8"))
        except (OSError,ValueError,UnicodeError) as exc:
            raise AnalyticsError("Metricool inbox malformed") from exc
        rows, collected=validate_inbox(payload,source.name)
        doc=convert(rows,collected_at=collected)
        prepared.append((dest,doc))
    # Prepare and validate everything before writing any snapshots.
    for dest,doc in prepared:
        save(doc,dest)
    return {"status":"IMPORTED","imported":len(prepared),"skipped_existing":skipped}


def main() -> int:
    try:
        result=process_inbox()
    except (AnalyticsError,ValueError,OSError,TypeError):
        print(json.dumps({"status":"BLOCKED","reason":"Metricool inbox validation failed"}))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
