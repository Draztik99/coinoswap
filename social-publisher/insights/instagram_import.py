"""Import a read-only Metricool IG feed-post metrics response into immutable JSON.

This CLI accepts Metricool connector's field-ordered rows, not a social token.
It cannot post, schedule, or update Metricool. Feed post rows are collected
only if they match the official CoinoSwap Daily Rates campaign.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from model import SAST, IG_FIELDS, AnalyticsError, instagram_metricool_row


def convert(payload: object, *, collected_at: datetime) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise AnalyticsError("invalid Metricool post analytics response")
    rows = payload["rows"]
    if len(rows) > 1000:
        raise AnalyticsError("too many Metricool rows")
    posts = []
    seen = set()
    for row in rows:
        item = instagram_metricool_row(row, collected_at=collected_at)
        caption = item["caption"].lower()
        if not ("crypto price check" in caption and "$btc" in caption
                and "$eth" in caption and "$xmr" in caption):
            continue
        if item["provider_post_id"] in seen:
            raise AnalyticsError("duplicate Metricool post ID")
        seen.add(item["provider_post_id"])
        posts.append(item)
    return {
        "schema_version":1,
        "provider":"Metricool connector / read-only feed post metrics",
        "metric_field_ids":list(IG_FIELDS),
        "brand_id":"8283300",
        "collected_at_sast":collected_at.astimezone(SAST).isoformat(timespec="seconds"),
        "records":posts,
    }


def save(payload: dict, path: Path) -> None:
    path=Path(path)
    if path.suffix!=".json":
        raise AnalyticsError("only JSON snapshot output is allowed")
    if path.exists():
        raise AnalyticsError("Metricool snapshot exists: immutable daily snapshot")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as file:
        json.dump(payload,file,indent=2,sort_keys=True,ensure_ascii=False)
        file.write("\n")


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Import Metricool Instagram analytics, NO POST")
    p.add_argument("--input",required=True)
    p.add_argument("--collected-at",required=True,help="Timezone-aware ISO SAST timestamp")
    p.add_argument("--output",required=True)
    a=p.parse_args(argv)
    try:
        t=datetime.fromisoformat(a.collected_at)
        if t.utcoffset() is None:
            raise AnalyticsError("timezone missing")
        source=Path(a.input)
        if not source.is_file() or source.stat().st_size>512_000:
            raise AnalyticsError("Metricool export absent or oversized")
        data=json.loads(source.read_text(encoding="utf-8"))
        result=convert(data,collected_at=t)
        save(result,Path(a.output))
    except (AnalyticsError, OSError, ValueError, UnicodeError, TypeError):
        print("BLOCKED: Metricool analytics import not validated")
        return 2
    print(json.dumps({"status":"IMPORTED","posts":len(result["records"]),
                      "output":a.output}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
