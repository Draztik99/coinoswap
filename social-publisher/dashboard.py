"""Static, read-only HTML dashboard generator.

No live social, website or swap integrations are wired. Default dashboard
renders unavailable values as 'N/A' and NEVER invents zero activity.
"""
from __future__ import annotations

import argparse
import html
from datetime import datetime
from pathlib import Path

SAST_SUFFIX = "Africa/Johannesburg"
PLATFORMS = (("x", "X"), ("facebook", "Facebook"), ("instagram", "Instagram"))


class DashboardRejected(ValueError):
    pass


def _safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def _integer(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DashboardRejected("dashboard metrics must be nonnegative integer or missing")
    return f"{value:,}"


def _decimal(value: object) -> str:
    if value is None:
        return "N/A"
    from decimal import Decimal, InvalidOperation
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DashboardRejected("invalid dollar value") from exc
    if not amount.is_finite() or amount < 0:
        raise DashboardRejected("negative/nonfinite dollar value")
    return f"US$ {amount:,.2f}"


def _rate(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not 0 <= value <= 1:
        raise DashboardRejected("invalid engagement rate")
    return f"{value*100:.2f}%"


def render_dashboard(snapshot: dict | None = None) -> str:
    if snapshot is None:
        snapshot = {}
    if not isinstance(snapshot, dict):
        raise DashboardRejected("snapshot must be a mapping")
    platforms = snapshot.get("platforms", {})
    if not isinstance(platforms, dict):
        raise DashboardRejected("platform values invalid")
    website = snapshot.get("website", {})
    swaps = snapshot.get("swaps", {})
    if not isinstance(website, dict) or not isinstance(swaps, dict):
        raise DashboardRejected("funnel values invalid")
    source_date = snapshot.get("as_of_sast") or "Not connected"
    environment = snapshot.get("environment") or "SHADOW / NO LIVE DATA"
    cards = [
        ("Website sessions",_integer(website.get("sessions")), "UTM-tracked sessions"),
        ("Completed swaps",_integer(swaps.get("verified_completed")), "Only backend-verified completions"),
        ("Attributed swaps",_integer(swaps.get("attributed_completed")), "Exact session -> swap linkage"),
        ("Completed volume",_decimal(swaps.get("volume_usd")), "Confirmed USD equivalent"),
    ]
    card_html = "".join(
        '<article class="metric"><div class="label">'+_safe(label)+'</div>'
        '<div class="value">'+_safe(value)+'</div><div class="detail">'+_safe(detail)+'</div></article>'
        for label,value,detail in cards
    )
    rows=[]
    for key,label in PLATFORMS:
        data = platforms.get(key) or {}
        if not isinstance(data, dict):
            raise DashboardRejected("invalid platform data")
        row = (
            "<tr><td><strong>"+_safe(label)+"</strong></td>"
            "<td>"+_safe(data.get("status") or "Not connected")+"</td>"
            "<td>"+_integer(data.get("impressions"))+"</td>"
            "<td>"+_integer(data.get("views"))+"</td>"
            "<td>"+_integer(data.get("engagements"))+"</td>"
            "<td>"+_rate(data.get("engagement_rate"))+"</td>"
            "<td>"+_integer(data.get("link_clicks"))+"</td></tr>"
        )
        rows.append(row)
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CoinoSwap | Social Publishing Analytics</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;padding:32px;background:#111110;color:#f1ede2;font:15px/1.55 system-ui,Arial,sans-serif}
.container{max-width:1180px;margin:0 auto}
h1{margin:0;font-size:29px;letter-spacing:-.02em}h2{margin-top:38px;font-size:18px}
.gold{color:#e6b852}.eyebrow{font-size:12px;letter-spacing:.13em;color:#e6b852;font-weight:700}
.muted{color:#a8a499;font-size:13px}.top{display:flex;justify-content:space-between;gap:20px;align-items:start;flex-wrap:wrap}
.state{padding:7px 11px;border:1px solid #735c30;color:#e6b852;border-radius:100px;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;margin-top:28px}
.metric{border:1px solid #37322a;background:#1c1b18;padding:20px;border-radius:13px}
.label{color:#b9b3a6;font-size:13px}.value{font-size:25px;font-weight:700;margin:8px 0;color:#e6b852}
.detail{font-size:12px;color:#aaa493}table{width:100%;border-collapse:collapse;min-width:690px}
th,td{padding:14px;text-align:left;border-bottom:1px solid #37322a}
th{color:#baa36f;font-weight:600;font-size:12px}td{font-size:13px}
.table-wrap{overflow-x:auto;background:#191815;border:1px solid #37322a;border-radius:12px;padding:0 12px}
footer{margin-top:30px;color:#a8a499;font-size:12px}
@media(max-width:750px){body{padding:18px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:24px}}
</style></head><body>
<main class="container">
<div class="top"><div><div class="eyebrow">COINOSWAP · ANALYTICS</div>
<h1>Direct Social Publishing</h1><p class="muted">As of __DATE__ · __TIMEZONE__</p></div>
<div class="state">__ENVIRONMENT__</div></div>
<div class="grid">__CARDS__</div>
<h2>Per-platform performance</h2>
<div class="table-wrap"><table><thead><tr><th>Channel</th><th>Publishing</th>
<th>Impressions</th><th>Views</th><th>Engagements</th><th>Eng. rate</th><th>Link clicks</th>
</tr></thead><tbody>__ROWS__</tbody></table></div>
<footer>Missing or unsupported data displays N/A, not 0. Instagram caption links are
not clickable. Swap completions require independently verified backend events.
This file is a read-only preview and does not publish social content.</footer>
</main></body></html>"""
    return (page.replace("__DATE__", _safe(source_date))
        .replace("__TIMEZONE__", SAST_SUFFIX)
        .replace("__ENVIRONMENT__", _safe(environment))
        .replace("__CARDS__", card_html)
        .replace("__ROWS__", "".join(rows)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build offline empty dashboard. No API calls.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    target=Path(args.output)
    if target.suffix.lower() != ".html":
        parser.error("only .html output is supported")
    target.write_text(render_dashboard(),encoding="utf-8")
    print("SHADOW dashboard created with N/A placeholders:",target)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
