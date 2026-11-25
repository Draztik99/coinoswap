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

    # Aggregate only measured values. Unknown != zero; explicitly show coverage.
    def platform_summary(platform):
        group=[p for p in posts if p["platform"]==platform]
        measured=[p for p in group if p.get("collected_at_sast")]
        def total(field):
            vals=[p["metrics"].get(field) for p in group]
            known=[v for v in vals if v is not None]
            return (f"{sum(known):,}" if known else "N/A",len(known),len(vals))
        reach,reach_covered,denom=total("reach")
        views,views_covered,_=total("views")
        actions,actions_covered,_=total("interactions")
        freshness=_latest_sync(posts,platform=platform,now=now)
        return ('<article class="platform-card"><div class="platform-head"><div>'
                '<div class="eyebrow">'+_esc(platform.upper())+'</div>'
                '<h3>'+_esc(platform.title())+'</h3></div>'
                '<span class="tiny-pill">'+_esc(len(group))+(" post" if len(group)==1 else " posts")+'</span></div>'
                '<div class="platform-grid">'
                '<div><span>Measured reach</span><strong>'+_esc(reach)+'</strong>'
                '<small>'+_esc(reach_covered)+' / '+_esc(denom)+' available</small></div>'
                '<div><span>Views</span><strong>'+_esc(views)+'</strong>'
                '<small>'+_esc(views_covered)+' / '+_esc(denom)+' available</small></div>'
                '<div><span>Interactions</span><strong>'+_esc(actions)+'</strong>'
                '<small>'+_esc(actions_covered)+' / '+_esc(denom)+' available</small></div></div>'
                '<p class="platform-foot">'+_esc(len(measured))+' measured records · '+_esc(freshness)+'</p>'
                '</article>')
    platform_cards=platform_summary("facebook")+platform_summary("instagram")
    # Reach bars are individual measured posts, not an invented continuous trend.
    reach_posts=[p for p in posts[:90] if p["metrics"].get("reach") is not None]
    if len(reach_posts)>=2:
        peaks=max(p["metrics"]["reach"] for p in reach_posts)
        reach_bars="".join(
            '<div class="reach-row"><div class="reach-meta"><span>'
            +_esc(p["platform"].title()+" · "+p["date_sast"])+'</span><b>'
            +_esc(f'{p["metrics"]["reach"]:,}')+'</b></div>'
            +'<div class="track"><div class="fill" style="width:'
            +str(round(100*p["metrics"]["reach"]/peaks,1) if peaks else 0)
            +'%"></div></div></div>'
            for p in reach_posts[:12]
        )
        chart_note="Up to 12 recent posts with measured reach. Missing values excluded."
    else:
        reach_bars='<p class="empty">A reach comparison needs at least two posts with measured reach. No values have been estimated.</p>'
        chart_note="Waiting for comparable verified reach measurements."
    data_quality=(
        f'{measured} of {len(posts)} posts have metric snapshots. '
        f'{sum(p["metrics"].get("reach") is not None for p in posts)} have measured reach. '
        'Unknown measurements remain N/A; totals include only known values.'
    )

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
:root{color-scheme:dark;--bg:#0d0e10;--panel:#191a1d;--panel2:#151618;--stroke:#37332b;--gold:#e8bd64;--goldsoft:#bda06c;--ink:#f5f1e8;--muted:#b7afa0;--quiet:#918c85}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-width:320px;padding:0;background:radial-gradient(ellipse at 15% 0%,#292319 0,transparent 36%),var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}main{max-width:1440px;margin:0 auto;padding:34px 34px 60px}a{color:var(--gold);text-underline-offset:3px}a:hover{color:#ffdc96}a:focus-visible{outline:2px solid var(--gold);outline-offset:4px;border-radius:3px}.eyebrow{font-size:11px;letter-spacing:.19em;color:var(--gold);font-weight:800;text-transform:uppercase}h1{font-size:clamp(26px,3.2vw,40px);letter-spacing:-.04em;line-height:1.12;margin:10px 0 14px;font-weight:750}h2{font-size:21px;letter-spacing:-.02em;margin:0 0 8px}h3{margin:5px 0 0;font-size:22px}p{margin:0 0 16px}.muted,.note{color:var(--muted);font-size:13px}.head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;flex-wrap:wrap;padding:12px 0 26px;border-bottom:1px solid var(--stroke)}.head .muted{margin:0}.pill,.tiny-pill{display:inline-flex;align-items:center;gap:7px;border:1px solid #70572d;border-radius:99px;padding:7px 13px;color:var(--gold);font-size:11px;letter-spacing:.055em;font-weight:700}.tiny-pill{border-color:#454137;padding:4px 9px;color:var(--muted);letter-spacing:0}.topnav{display:flex;gap:10px;flex-wrap:wrap;margin-top:19px}.topnav a{display:inline-block;padding:7px 12px;border:1px solid var(--stroke);background:#161618;border-radius:8px;text-decoration:none;font-size:12px;color:var(--muted)}.topnav a:hover{border-color:var(--gold);color:var(--gold)}.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap;margin:34px 0 16px}.section-head p{margin:0}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:22px 0 10px}.card{background:linear-gradient(160deg,#222019,var(--panel) 70%);border:1px solid var(--stroke);border-radius:15px;padding:21px;min-height:136px}.card-label{font-size:12px;color:#c4b9a8}.card-value{font-size:clamp(24px,2.8vw,34px);letter-spacing:-.025em;color:var(--gold);font-weight:800;margin:11px 0 5px}.note{font-size:11px}.platform-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.platform-card,.reach-card,.quality-card{background:var(--panel2);border:1px solid var(--stroke);border-radius:15px;padding:22px}.platform-head{display:flex;justify-content:space-between;align-items:start;gap:15px}.platform-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:20px}.platform-grid div{border-right:1px solid #302e2b;padding-right:8px;min-width:0}.platform-grid div:last-child{border:0}.platform-grid span,.platform-grid small{display:block;color:var(--muted);font-size:11px}.platform-grid strong{display:block;font-size:25px;color:var(--gold);margin:4px 0;letter-spacing:-.03em}.platform-foot{color:var(--muted);font-size:11px;margin:17px 0 0;padding-top:12px;border-top:1px solid var(--stroke)}.analysis-grid{display:grid;grid-template-columns:1.15fr 1fr;gap:16px}.reach-meta{display:flex;justify-content:space-between;gap:10px;font-size:12px;margin:10px 0 6px}.reach-meta span{color:var(--muted)}.track{height:9px;background:#333029;border-radius:12px;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#916929,#f2cd7c);border-radius:12px}.empty{border:1px dashed #4e4435;border-radius:10px;padding:19px;color:var(--muted);font-size:13px;margin:15px 0}.quality-card p{color:var(--muted);font-size:13px;line-height:1.7}.quality-card strong{color:var(--ink)}.report-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:25px 0 16px}.download{padding:11px 16px;background:var(--gold);color:#181713;border-radius:9px;font-weight:800;font-size:12px;text-decoration:none}.download:hover{background:#ffdc91;color:#181713}.table-scroll{overflow-x:auto;border:1px solid var(--stroke);border-radius:13px;scrollbar-color:#94713f #1b1b1b}table{width:100%;min-width:960px;border-collapse:collapse;background:#171719}th,td{padding:15px 13px;text-align:left;border-bottom:1px solid #34302b;font-size:12px;white-space:nowrap}th{text-transform:uppercase;letter-spacing:.055em;color:#ffda89;font-size:12px;font-weight:800;background:#2c281f;position:sticky;top:0;white-space:nowrap;text-shadow:0 1px 1px #111}tbody tr:hover{background:#27231c}tbody tr:last-child td{border-bottom:0}.status-note{color:var(--muted);font-size:12px;margin:12px 0 0}.measurement{padding:20px;background:#18191b;border:1px solid var(--stroke);border-radius:13px;color:var(--muted);font-size:13px;line-height:1.7}footer{margin-top:29px;padding-top:17px;border-top:1px solid var(--stroke);color:var(--quiet);font-size:11px}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.analysis-grid{grid-template-columns:1fr}}@media(max-width:700px){main{padding:18px 15px 48px}.head{padding-top:9px}.platform-layout{grid-template-columns:1fr}.platform-card,.reach-card,.quality-card{padding:17px}.card{padding:17px;min-height:124px}.platform-grid strong{font-size:21px}.report-bar{align-items:flex-start}.grid{gap:9px}}@media(max-width:370px){.grid{grid-template-columns:1fr}.platform-grid{gap:7px}}
</style></head><body><main>
<div class="head"><div><div class="eyebrow">COINOSWAP / PERFORMANCE INTELLIGENCE</div><h1>Social Publishing Analytics</h1>
<p class="muted">Report generated __ASOF__ · SAST (UTC+2) · Verified snapshots only</p><nav class="topnav" aria-label="Dashboard sections"><a href="#channels">Platform overview</a><a href="#insights">Reach insights</a><a href="#performance">Post performance</a><a href="#methodology">Data quality</a></nav></div><span class="pill">● READ-ONLY REPORTING</span></div>
<div class="section-head"><div><div class="eyebrow">OVERVIEW</div><h2>At a glance</h2></div><p class="muted">Public aggregate social metrics · no estimates</p></div><div class="grid">__CARDS__</div>
<section id="channels"><div class="section-head"><div><div class="eyebrow">CHANNELS</div><h2>Platform performance</h2></div></div><div class="platform-layout">__PLATFORMS__</div></section>
<section id="insights"><div class="section-head"><div><div class="eyebrow">INSIGHTS</div><h2>Reach & data confidence</h2></div></div><div class="analysis-grid"><article class="reach-card"><h3>Measured post reach</h3><p class="muted">__REACH_NOTE__</p>__REACH_BARS__</article><article class="quality-card"><h3>Reporting confidence</h3><p>__QUALITY__</p><p><strong>Interpretation:</strong> N/A means a metric has not been measured, not that its value is zero. Coverage is shown alongside every aggregate.</p><p><strong>Freshness:</strong> This is a build-time snapshot. Changes to underlying data require a new successful collection and deployment.</p></article></div></section>
<section id="performance"><div class="section-head"><div><div class="eyebrow">POSTS</div><h2>Publication performance</h2></div><p class="muted">Latest 90 verified posts</p></div><div class="report-bar"><p class="muted">Facebook latest metrics: __FB_SYNC__ · Instagram latest metrics: __IG_SYNC__</p></div>
<div class="table-scroll" role="region" aria-label="Verified publication performance table" tabindex="0"><table><thead><tr>
<th>Platform</th><th>Published SAST</th><th>Selected daily slot</th>
<th>Reach</th><th>Views</th><th>Interactions</th><th>Comments</th><th>Age</th><th>Metrics sync</th><th>Source</th>
</tr></thead><tbody>__ROWS__</tbody></table></div><p class="status-note">Only measured values are shown. Off-slot posts are labeled; no unsupported attribution is inferred.</p></section>
<section id="methodology"><div class="section-head"><div><div class="eyebrow">TRANSPARENCY</div><h2>Measurement status</h2></div></div><div class="measurement">Facebook receives read-only Graph snapshots from verified publication receipts.
Instagram currently uses Metricool feed-post metrics. X, website UTM sessions, and backend-verified completed swaps
are not connected. Missing and unsupported counts show N/A, not zero.
Only posts aged 24+ hours are eligible for mature-post comparisons. Off-slot/manual posts are excluded
from randomized-slot rankings.</div></section>
<footer>Source: CoinoSwap official GitHub + Meta Graph API + Metricool. No Facebook or Instagram posts can be created from this dashboard.</footer>
</main></body></html>"""
    return (template.replace("__ASOF__",_esc(now.isoformat(timespec="minutes")))
        .replace("__CARDS__",cards).replace("__ROWS__",table_html)
        .replace("__FB_SYNC__",_esc(fb_sync)).replace("__IG_SYNC__",_esc(ig_sync))
        .replace("__PLATFORMS__",platform_cards).replace("__REACH_BARS__",reach_bars)
        .replace("__REACH_NOTE__",_esc(chart_note)).replace("__QUALITY__",_esc(data_quality)))

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
