"""Build a minimal Cloudflare Pages site for the CoinoSwap team dashboard.

Security properties:
- CLOSED by default: Cloudflare initially serves only a placeholder.
- Live dashboard export needs *both* the production Git branch and an operator
  acknowledgement that Access protects the production hostname and previews.
- Acknowledgement is a deployment interlock, NOT an authentication mechanism.
  Cloudflare Access must enforce authentication at the network edge.
- Only approved, aggregate social post data is exported: no raw snapshots,
  pricing manifests, credentials, events, session identifiers or swap records.
- No HTTP/API calls, and no social publishing.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Mapping

from dashboard import load_posts, render
from model import FIELDS, SAST

ACCESS_FLAG = "COINOSWAP_TEAM_ACCESS_VERIFIED"
PRODUCTION_BRANCH = "main"
HEADERS = """/*
  X-Robots-Tag: noindex, nofollow, noarchive
  Referrer-Policy: no-referrer
  X-Content-Type-Options: nosniff
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Content-Security-Policy: default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
  Cache-Control: private, no-store, max-age=0
"""
PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>CoinoSwap Analytics | Provisioning</title>
<style>
:root{color-scheme:dark}body{box-sizing:border-box;min-height:100vh;margin:0;
display:grid;place-items:center;padding:24px;background:#10100f;color:#ece9df;
font:16px/1.6 system-ui,-apple-system,Arial,sans-serif}
section{max-width:540px;border:1px solid #4a3a21;border-radius:16px;
padding:32px;background:#1b1a17}h1{margin:5px 0;font-size:26px}
small{color:#dfb967;letter-spacing:.14em;font-weight:700}
p{color:#bcb6a9}code{color:#f2cd86}
</style></head><body><section>
<small>COINOSWAP / TEAM ANALYTICS</small>
<h1>Private dashboard provisioning</h1>
<p>This deployment intentionally contains no analytics data. Team access must be
configured and verified before report delivery is activated.</p>
<p>Contact the CoinoSwap dashboard administrator for access.</p>
</section></body></html>
"""

COLUMNS = (
    "platform", "post_date_sast", "published_time_sast", "provider_post_id",
    "publication_status", "reach", "views", "reactions", "likes",
    "comments", "shares", "saves", "interactions", "link_clicks", "public_post_url",
)


def access_release_ready(environ: Mapping[str, str]) -> bool:
    """Fail closed for unset flags and all preview branch deployments."""
    return (
        environ.get("CF_PAGES_BRANCH") == PRODUCTION_BRANCH
        and environ.get(ACCESS_FLAG) == "true"
    )


def _safe_csv(value: object) -> str:
    """Prevent Excel/LibreOffice formula evaluation in downloaded reports."""
    if value is None:
        return "N/A"
    item = str(value)
    # Excel may ignore whitespace before a formula; guard the first content char.
    if item.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + item
    return item


def csv_report(posts: list[dict]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for post in posts:
        metrics = post["metrics"]
        if set(metrics) != set(FIELDS):
            raise ValueError("unexpected social metric schema")
        stamp = datetime.fromisoformat(post["published_at_sast"]).astimezone(SAST)
        row = (
            post["platform"], post["date_sast"], stamp.strftime("%H:%M:%S"),
            post["provider_post_id"], post["status"],
            *(metrics[name] for name in (
                "reach","views","reactions","likes","comments","shares",
                "saves","interactions","link_clicks"
            )),
            post["public_url"],
        )
        writer.writerow([_safe_csv(x) for x in row])
    return buf.getvalue()


def build(*, root: Path, output: Path, environ: Mapping[str, str],
          at: datetime | None = None) -> dict:
    root = Path(root).resolve()
    output = Path(output).absolute()
    if output.name != "dist" or output.is_symlink() or output == root:
        raise ValueError("output must be a dedicated, non-symlink dist directory")
    # Never leave an old report or CSV behind after switching to locked mode.
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / "_headers").write_text(HEADERS, encoding="utf-8")
    (output / "robots.txt").write_text(
        "User-agent: *\nDisallow: /\n", encoding="utf-8"
    )
    if not access_release_ready(environ):
        (output / "index.html").write_text(PLACEHOLDER, encoding="utf-8")
        return {"status":"LOCKED_PLACEHOLDER", "data_files_exported":0,
                "files":[p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()]}

    now = at or datetime.now(SAST)
    posts = load_posts(
        facebook_receipts=root / "docs/daily-rates/facebook-publications",
        snapshots=root / "docs/social-analytics/snapshots",
    )
    page = render(posts=posts, now=now)
    if "<h2>Publication performance</h2>" not in page:
        raise ValueError("unexpected dashboard template")
    page = page.replace(
        "<h2>Publication performance</h2>",
        '<h2>Publication performance</h2><p class="download-wrap">'
        '<a class="download" href="/reports/post-performance.csv" download>Download post report (CSV)</a>'
        '</p>',
        1,
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    reports_dir = output / "reports"
    reports_dir.mkdir()
    (reports_dir / "post-performance.csv").write_text(
        csv_report(posts), encoding="utf-8"
    )
    # Entire deployable output is intentionally constrained to four files.
    files = sorted(p.relative_to(output).as_posix()
                   for p in output.rglob("*") if p.is_file())
    if files != ["_headers", "index.html", "reports/post-performance.csv", "robots.txt"]:
        raise ValueError("build attempted to export an unexpected file")
    return {"status":"PRIVATE_DASHBOARD_ARTIFACT_BUILT",
            "posts":len(posts), "data_files_exported":1, "files":files}


def main() -> int:
    parser=argparse.ArgumentParser(description="Build Cloudflare Pages dashboard (locked by default)")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="dist")
    args=parser.parse_args()
    import json
    print(json.dumps(build(root=Path(args.root),output=Path(args.output),
                           environ=os.environ),sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
