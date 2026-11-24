# CoinoSwap Social Analytics — v1 data collection (24 November 2026)

This milestone begins **now**, while X and Instagram-direct publishing remain in development.

## Verified inputs and boundaries

- **Facebook:** The CoinoSwap Page Graph API is verified with the Page access token in the protected `facebook-live` environment. Only independently verified `docs/daily-rates/facebook-publications/YYYY-MM-DD.json` receipts qualify for metrics. A scheduled **GET-only** collector requests per-post reactions, comments, shares, and optional `post_media_view` using v27.0. Missing or unsupported metrics remain `null`, never zero.
- **Instagram:** The connected Metricool brand ID is `8283300`, with timezone `Africa/Johannesburg`. Metricool's read-only analytics connector returned a real 22 November Daily Rates feed post. Its snapshot was imported and preserved in `docs/social-analytics/snapshots/instagram/2026-11-24.json`; it is NOT synthetic demo data.
- **X:** no X API OAuth credentials or live metrics yet.
- **Website/swap attribution:** no verified session/swaps provider is connected, so the dashboard never claims visits, completed swaps or volume.
- **Privacy:** only brand-owned published post IDs, public URLs, timestamps and aggregate counts are stored. No page token, user identities, private comments or session identifiers are exported.
- **Publishing:** The analytics modules and workflow perform **no social POST** or schedule changes. The existing Daily Rates Facebook direct workflow and Instagram Metricool automations are unaffected.

## Snapshot layout

- `docs/social-analytics/snapshots/facebook/YYYY-MM-DD/YYYY-MM-DD.json`: one immutable Facebook metrics observation per **post date / observation date**; collected daily for verified posts up to 32 days old.
- `docs/social-analytics/snapshots/instagram/YYYY-MM-DD.json`: immutable Metricool connector export, containing one or more feed-post records and an explicit metric-field order.
- `docs/social-analytics/index.html`: static black-and-gold dashboard, generated from the latest verified snapshot per post plus publication receipts.
- Historical observations are retained, so post growth can be compared around 24h / 7d / 30d and posting-slot analysis can be added without inventing historical values.

## Daily jobs and failure rules

`.github/workflows/coinoswap-social-analytics.yml` runs at 17:05 UTC (**19:05 SAST**), after the randomized posting window, and can also be run manually. It uses the `facebook-live` **secret for read-only Meta GETs**, never passes a token in a URL, and never creates social posts. The job checks credentials and post ownership, then appends Facebook data and regenerates the HTML dashboard. Missing token, invalid Page identity, wrong post ID, denied mandatory Graph GET or malformed provider data makes the job fail. `post_media_view` is optional: if unsupported, the field remains unavailable.

GitHub schedule dispatch is best-effort. A missing daily analytics run must not be mistaken for fresh data; the dashboard reports the timestamp of each snapshot. The collector performs a maximum of one observation per post per SAST day and never overwrites old measurements.

## Instagram automation limitation and next connector milestone

The Metricool **ChatGPT connector** is active and can read Instagram analytics now, but its credential is **not available inside GitHub Actions**. Metricool's programmatic HTTP API requires separate eligible-plan access and a secure API token. The v1 implementation therefore provides an audited, immutable `instagram_import.py` path for further connected exports, not a claim of unattended Instagram metrics refresh. Before enabling GitHub-native daily Instagram collection, verify plan/API access and exact supported endpoint/auth in the actual account. Do not expose a Metricool token or change Instagram scheduling.

Example: import a Metricool analytics JSON export with the exact field IDs `IGPO02 IGPO03 IGPO04 IGPO06 IGPO08 IGPO10 IGPO12 IGPO13 IGPO14 IGPO15 IGPO27 IGPO28`:

```bash
python social-publisher/insights/instagram_import.py \
  --input metricool-posts.json \
  --collected-at 2026-11-24T19:48:08+02:00 \
  --output docs/social-analytics/snapshots/instagram/2026-11-24.json
```

The example date is already imported. Never overwrite an existing snapshot; use a new collection date.

## Dashboard semantics

- A verified Facebook publication is shown even before any analytics response, with metrics marked `N/A`.
- `0` is reserved for an explicitly measured zero. `N/A` denotes missing/denied/unsupported measurements.
- Randomized slot labels are only assigned when the actual published clock time matches that day's deterministic selection. Off-slot emergency posts are not included in timed-experiment comparisons.
- A posting-time comparison is only meaningful for equivalent post ages; the dashboard marks recent posts under 24h and only ranks reach for mature posts.
- No post metric is conflated with website referrals or completed swaps.
- The HTML is stored in GitHub and can be downloaded. A GitHub Pages URL is **not assumed live** until repository Pages settings are verified separately.

## Next milestones

1. Run and verify the read-only Facebook collector against Meta in the protected GitHub environment.
2. Enable an **eligible** Metricool analytics API collector, or export supported Instagram data through the connected plugin without extra credential exposure.
3. Track UTM-tagged website visits with the existing website analytics stack (once verified).
4. Connect backend-verified unique completed swap events, then compute channel/slot conversion funnels.
5. Add X to the same schema after developer authorization and the first independently verified live X post.

## Provider references (verified 2026-11-24)

- Meta Post Insights: https://developers.facebook.com/docs/graph-api/reference/post/insights/
- Meta Page Insights deprecations: https://developers.facebook.com/docs/graph-api/reference/insights/
- Metricool API access eligibility: https://help.metricool.com/plans-add-ons-and-api-access-explained-xux1u
- Metricool API vs connector: https://help.metricool.com/mcp-vs-api-access-what-is-the-difference-5y3ib
