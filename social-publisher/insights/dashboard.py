"""Static black-and-gold CoinoSwap social analytics dashboard from verified data.

No network calls, post creation, or user-data inference. Missing metrics stay N/A.
All HTML is escaped, no client-side API credentials or third-party scripts.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"daily-rates"))
from model import FIELDS, PAGE_ID, SAST, safe_url, AnalyticsError
from posting_slots import slot_for_date

FACEBOOK_RECEIPTS=Path("docs/daily-rates/facebook-publications")
SNAPSHOTS=Path("docs/social-analytics/snapshots")
OUTPUT=Path("docs/social-analytics/index.html")

def _esc(value):
    return html.escape(str(value),quote=True)

def _metric(value):
    if value is None:
        return "N/A"
    if isinstance(value,bool) or not isinstance(value,int) or value<0:
        raise AnalyticsError("invalid dashboard metric")
    return f"{value:,}"

def _read_json(path: Path):
    if path.stat().st_size>256_000:
        raise AnalyticsError("analytics source exceeds safe size")
    return json.loads(path.read_text(encoding="utf-8"))

def _timestamp(record):
    try:
        t=datetime.fromisoformat(record["published_at_sast"])
        if t.tzinfo is None or t.utcoffset() is None:
            raise ValueError("naive")
        return t.astimezone(SAST)
    except (KeyError,TypeError,ValueError) as exc:
        raise AnalyticsError("invalid post publication time") from exc

def select_latest_snapshots(root: Path) -> dict:
    result={}
    if not root.is_dir():
        return result
    for path in sorted(root.glob("**/*.json")):
        obj=_read_json(path)
        records=obj.get("records") if isinstance(obj,dict) and "records" in obj else [obj]
        if not isinstance(records,list):
            raise AnalyticsError("invalid analytics batch")
        for record in records:
            if not isinstance(record,dict) or record.get("platform") not in {"facebook","instagram"}:
                raise AnalyticsError("invalid analytics post")
            pid=record.get("provider_post_id")
            if not isinstance(pid,str) or not pid:
                raise AnalyticsError("missing verified post ID")
            key=(record["platform"],pid)
            observed=record.get("collected_at_sast")
            if not isinstance(observed,str):
                raise AnalyticsError("missing snapshot collection timestamp")
            try:
                dt=datetime.fromisoformat(observed)
                if dt.tzinfo is None or dt.utcoffset() is None:
                    raise ValueError()
            except ValueError as exc:
                raise AnalyticsError("invalid analytics collection time") from exc
            if key not in result or dt>datetime.fromisoformat(result[key]["collected_at_sast"]):
                result[key]=record
    return result

def load_posts(*, facebook_receipts: Path=FACEBOOK_RECEIPTS,
               snapshots: Path=SNAPSHOTS) -> list[dict]:
    latest=select_latest_snapshots(snapshots)
    results=[]
    if facebook_receipts.is_dir():
        for path in sorted(facebook_receipts.glob("*.json")):
            r=_read_json(path)
            if (not isinstance(r,dict) or r.get("platform")!="facebook"
                    or r.get("status")!="PUBLISHED"
                    or r.get("verification")!="META_PAGE_PHOTO_READBACK"
                    or r.get("page_id")!=PAGE_ID or r.get("date_sast")!=path.stem):
                raise AnalyticsError("invalid verified Facebook receipt")
            pid=r.get("provider_post_id")
            if not isinstance(pid,str) or not pid.startswith(PAGE_ID+"_"):
                raise AnalyticsError("incorrect Page post reference")
            link=safe_url(r.get("public_url"),{"facebook.com","www.facebook.com","m.facebook.com"})
            post=latest.get(("facebook",pid))
            if post is not None and (post.get("date_sast")!=r["date_sast"]
                                     or post.get("public_url")!=link):
                raise AnalyticsError("Facebook metrics mismatch verified receipt")
            results.append({
                "platform":"facebook", "provider_post_id":pid,
                "date_sast":r["date_sast"],
                "published_at_sast":r["published_at_sast"],
                "public_url":link,
                "metrics":post["metrics"] if post else {name:None for name in FIELDS},
                "collected_at_sast":post["collected_at_sast"] if post else None,
                "status":"Measured" if post else "Metrics pending",
            })
    for (platform,_),post in latest.items():
        if platform!="instagram":
            continue
        safe_url(post.get("public_url"),{"instagram.com","www.instagram.com"})
        results.append({
            "platform":"instagram", "provider_post_id":post["provider_post_id"],
            "date_sast":post["date_sast"],
            "published_at_sast":post["published_at_sast"],
            "public_url":post["public_url"],"metrics":post["metrics"],
            "collected_at_sast":post["collected_at_sast"],"status":"Measured",
        })
    return sorted(results,key=_timestamp,reverse=True)

def _selected_slot(day):
    try:
        d=datetime.strptime(day,"%Y-%m-%d").date()
        h,m=slot_for_date(d)
        return f"{h:02d}:{m:02d}"
    except (ValueError,TypeError):
        return "N/A"

def _slot_label(post):
    selected=_selected_slot(post["date_sast"])
    actual=_timestamp(post).strftime("%H:%M")
    # Don't falsely credit late/manual posts to the randomized slot.
    return selected if selected==actual else "Manual / off-slot"

def _latest_sync(posts: list[dict], *, platform: str, now: datetime) -> str:
    stamps=[]
    for item in posts:
        if item.get("platform") != platform:
            continue
        raw=item.get("collected_at_sast")
        if raw is None:
            continue
        try:
            stamp_value=datetime.fromisoformat(raw)
            if stamp_value.tzinfo is None or stamp_value.utcoffset() is None:
                raise ValueError()
            stamps.append(stamp_value.astimezone(SAST))
        except (TypeError,ValueError,AttributeError) as exc:
            raise AnalyticsError("invalid metrics freshness timestamp") from exc
    if not stamps:
        return "No metrics collected"
    latest=max(stamps)
    seconds=(now-latest).total_seconds()
    if seconds < -60:
        raise AnalyticsError("future metrics timestamp")
    status="STALE" if seconds > 36*3600 else "Current"
    return f"{latest:%Y-%m-%d %H:%M} SAST · {status}"


def _card(label,number,note):
    return (f'<div class="card"><div class="card-label">{_esc(label)}</div>'
            f'<div class="card-value">{_esc(number)}</div><div class="note">{_esc(note)}</div></div>')

def render(*, posts: list[dict], now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise AnalyticsError("report clock must be timezone-aware")
    now=now.astimezone(SAST)
    fb=sum(p["platform"]=="facebook" for p in posts)
    ig=sum(p["platform"]=="instagram" for p in posts)
    measured=sum(p["collected_at_sast"] is not None for p in posts)
    mature=[p for p in posts if (now-_timestamp(p)).total_seconds()>=86400]
    comparable=[p for p in mature if p["metrics"].get("reach") is not None]
    best=max(comparable,key=lambda x:x["metrics"]["reach"]) if comparable else None
    best_txt=(f'{best["platform"].title()} · {best["metrics"]["reach"]:,}' if best else "N/A")
    cards=("".join([
        _card("Verified Facebook posts",str(fb),"GitHub Page receipts"),
        _card("Measured Instagram posts",str(ig),"Connected Metricool data"),
        _card("Posts with metric snapshots",f"{measured} / {len(posts)}","Missing values never become zero"),
        _card("Highest 24h+ post reach",best_txt,"Mature posts with actual reach only"),
    ]))
    fb_sync = _latest_sync(posts,platform="facebook",now=now)
    ig_sync = _latest_sync(posts,platform="instagram",now=now)
    table=[]
    for p in posts[:90]:
        date=p["date_sast"]
        t=_timestamp(p).strftime("%H:%M")
        metric=p["metrics"]
        for name in FIELDS:
            if name not in metric:
                raise AnalyticsError("incomplete metric schema")
        date_label=f"{date} · {t}"
        platform=p["platform"].title()
        age=(now-_timestamp(p)).total_seconds()/3600
        maturity="24h+" if age>=24 else "New (<24h)"
        last_sync=p.get("collected_at_sast")
        sync_label=(datetime.fromisoformat(last_sync).astimezone(SAST).strftime("%Y-%m-%d %H:%M")
                    if last_sync else "N/A")
        if last_sync and (now-datetime.fromisoformat(last_sync).astimezone(SAST)).total_seconds()>36*3600:
            sync_label+=" · STALE"
        table.append(
            "<tr><td>"+_esc(platform)+"</td><td>"+_esc(date_label)+"</td>"
            "<td>"+_esc(_slot_label(p))+"</td>"
            "<td>"+_esc(_metric(metric["reach"]))+"</td>"
            "<td>"+_esc(_metric(metric["views"]))+"</td>"
            "<td>"+_esc(_metric(metric["interactions"]))+"</td>"
            "<td>"+_esc(_metric(metric["comments"]))+"</td>"
            "<td>"+_esc(maturity)+"</td>"
            "<td>"+_esc(sync_label)+"</td>"
            '<td><a href="'+_esc(p["public_url"])+'" target="_blank" rel="noopener noreferrer">View post</a></td></tr>'
        )
    table_html="".join(table) if table else '<tr><td colspan="10">No verified posts yet. Metrics will appear after collection.</td></tr>'
    template="""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CoinoSwap | Social Analytics</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;padding:32px;background:#0e0e0d;color:#f7f3e7;font:15px/1.6 system-ui,-apple-system,Arial,sans-serif}
main{max-width:1280px;margin:auto}.eyebrow{font-size:12px;letter-spacing:.19em;color:#d6ad55;font-weight:800}
h1{font-size:32px;margin:4px 0}p{margin:0 0 18px}.muted,.note{color:#a7a192;font-size:12px}
.head{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;flex-wrap:wrap}
.pill{border:1px solid #82642f;border-radius:99px;padding:7px 12px;color:#ecc36e;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:26px 0 32px}
.card{background:#1b1a17;border:1px solid #3b3426;border-radius:14px;padding:20px;min-height:130px}
.card-label{font-size:12px;color:#bdb3a0}.card-value{font-size:27px;color:#e4b95e;font-weight:750;margin:8px 0 3px}
h2{font-size:18px;margin:32px 0 12px}.table-scroll{overflow-x:auto;border:1px solid #3b3426;border-radius:12px}
table{width:100%;min-width:850px;border-collapse:collapse;background:#171613}
th,td{padding:13px;text-align:left;border-bottom:1px solid #312d26;font-size:12px}
th{text-transform:uppercase;letter-spacing:.045em;color:#d5b06b}a{color:#eac474}
footer{margin-top:30px;color:#9c978d;font-size:12px}
@media(max-width:780px){body{padding:18px}.grid{grid-template-columns:repeat(2,1fr)}h1{font-size:25px}}
</style></head><body><main>
<div class="head"><div><div class="eyebrow">COINOSWAP / MEASURE WHAT MATTERS</div><h1>Social Publishing Analytics</h1>
<p class="muted">Updated __ASOF__ · Africa/Johannesburg</p></div><span class="pill">READ-ONLY · VERIFIED DATA</span></div>
<div class="grid">__CARDS__</div>
<h2>Publication performance</h2>
<p class="muted">Facebook latest metrics: __FB_SYNC__ · Instagram latest metrics: __IG_SYNC__</p>
<div class="table-scroll"><table><thead><tr>
<th>Platform</th><th>Published SAST</th><th>Selected daily slot</th>
<th>Reach</th><th>Views</th><th>Interactions</th><th>Comments</th><th>Age</th><th>Metrics sync</th><th>Source</th>
</tr></thead><tbody>__ROWS__</tbody></table></div>
<h2>Measurement status</h2><p class="muted">Facebook receives read-only Graph snapshots from verified publication receipts.
Instagram currently uses Metricool feed-post metrics. X, website UTM sessions, and backend-verified completed swaps
are not connected. Missing and unsupported counts show N/A, not zero.
Only posts aged 24+ hours are eligible for mature-post comparisons. Off-slot/manual posts are excluded
from randomized-slot rankings.</p>
<footer>Source: CoinoSwap official GitHub + Meta Graph API + Metricool. No Facebook or Instagram posts can be created from this dashboard.</footer>
</main></body></html>"""
    return (template.replace("__ASOF__",_esc(now.isoformat(timespec="minutes")))
        .replace("__CARDS__",cards).replace("__ROWS__",table_html)
        .replace("__FB_SYNC__",_esc(fb_sync)).replace("__IG_SYNC__",_esc(ig_sync)))

def build(*, receipts=FACEBOOK_RECEIPTS, snapshots=SNAPSHOTS, output=OUTPUT,
          now=None) -> dict:
    now=now or datetime.now(SAST)
    posts=load_posts(facebook_receipts=Path(receipts), snapshots=Path(snapshots))
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render(posts=posts,now=now),encoding="utf-8")
    return {"status":"BUILT","verified_posts":len(posts),"facebook_posts":sum(x["platform"]=="facebook" for x in posts),
            "instagram_posts":sum(x["platform"]=="instagram" for x in posts),
            "output":str(output)}

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Build read-only CoinoSwap dashboard")
    p.add_argument("--output",default=str(OUTPUT))
    a=p.parse_args()
    print(json.dumps(build(output=a.output),sort_keys=True))
