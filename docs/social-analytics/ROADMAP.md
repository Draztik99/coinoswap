# CoinoSwap Performance Intelligence — Integration Roadmap

Updated 2026-11-25 (SAST). This is a plan, not evidence that integrations are live.

## Guardrails
- Existing Instagram-only Metricool publishing automations must not be altered by analytics work. **Do not enable, schedule, or retry Facebook publishing.**
- Analytics jobs must be read-only; report missing metrics as N/A rather than zero.
- Repository is PUBLIC. Do not commit tokens, private attribution, individual swap records, customer identifiers, or other confidential analytics. Future protected metrics require private storage and runtime authentication, not just Cloudflare Access in front of files built from a public repository.
- Keep Cloudflare Access on production and previews; preserve locked preview builds and verify access to both HTML and CSV.
- Prefer free/low-cost paths; do not upgrade Metricool automatically.

## Roadmap and acceptance criteria (in order)

### 1. Source audit and Facebook/Instagram coverage — IN PROGRESS
- Instagram professional account is connected in the Metricool UI; YouTube also connected.
- Facebook Page shows "Connect a Facebook page" in Metricool. Meta Graph API read-only collector is separate from Metricool, and existing successful readbacks do not imply Metricool connection.
- Investigate why Metricool connector analytics API returns no post rows despite one Instagram post in UI. Verify connection method, permissions, time range, exact brand and provider responses. Do not replace existing Instagram connection casually: changing the connection type can affect available history.
- Backfill verified post-level public aggregates where legally available; retain provenance and coverage percentages; never assume Metricool's limited history means no older posts existed.
- Deliver source coverage, errors, stale thresholds, daily collection status, and tests.

### 2. Social analytics depth — PLANNED
- Platform comparisons, reach/views/interactions, normalized engagement only when the matching reach denominator is available, new-vs-mature post comparisons, and post date/slot analysis.
- Daily/weekly/monthly trends only when at least two measured points exist; avoid charting absent dates as zero.
- Explain metric scope (organic vs paid, post vs account) and connector version. Data snapshot timestamps in SAST.
- Include usable mobile layout, readable table headings, CSV exports and explicit freshness status.

### 3. X and YouTube — PLANNED
- YouTube: evaluate read-only metrics using existing connection; avoid claiming audience conversion without UTM/click evidence.
- X: determine actual API access and price constraints before connecting. Never infer engagement from posting automation alone.
- Do not exceed free-plan quotas merely to fill charts.

### 4. Website acquisition and conversion — PLANNED
- Use supported server-side aggregate web analytics and UTM tags to distinguish organic search, referral, paid and social sessions.
- Connect completed swaps/revenue only from secure verified backend aggregates. These must not be exported to the public repository.
- Attribution should be presented as directional unless privacy-safe deterministic evidence links a traffic event to a completed swap.

### 5. Google Search Console — FINAL ROADMAP INTEGRATION (PLANNED)
Property in user's Google Search Console UI: `coinoswap.com`; verify exact API property identifier and account permissions before requesting API access.

Initial screenshot baseline (16-month Web Search view at 2026-11-25; visually rounded, **not** imported data):
- 3.56K clicks
- 414K impressions
- 0.9% average CTR
- 15.8 average position

Read-only Search Analytics API integration should retrieve:
- Time series: clicks, impressions, CTR, average position by date.
- Rankings: top pages and top search queries, separately (privacy filtering and top-row limits mean these lists may not sum to total).
- Segments: country and device; search type set explicitly (Web by default).
- Windows: last 7/28/90 days and rolling 12/16-month view, with completed-day and processing-lag labeling.
- Comparisons: period-over-period, top rising/falling pages and queries, low-CTR high-impression opportunities; never treat position as an unweighted rank average or CTR as an arithmetic daily mean.
- Retain request metadata (property, dimensions, filters, date range, data state and collection time) and actual query coverage.
- Display aggregate SEO trends alongside — not as proof of — swap conversions.

Implementation design:
- Use least-privilege Google Search Console read-only OAuth scope and approved site property. Never share long-lived refresh tokens or service credentials in GitHub; use private secret storage and protected CI environment where available.
- Preserve aggregated metrics only where non-sensitive; do not commit proprietary landing-page/query intelligence to PUBLIC repository without an explicit publication decision. Prefer private storage/secure authenticated delivery for the full report.
- Schedule daily pulls accounting for Google processing lag and backfill revisions; enforce API quota/row pagination and retries.
- Unit-test aggregation, missing data, dates/time zones, duplicate handling, CSV safety, and schema validation before production.
- Do not modify DNS, the live CoinoSwap website or existing publishing workflows to connect Search Console.

Reference documentation:
- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data
- https://help.metricool.com/main-differences-between-free-and-paid-plans-bl0v9
- https://help.metricool.com/access-to-instagram-from-metricool-connection-types-and-differences-kcsrb

## Release gate
Each integration needs verified sample data, offline tests, source error handling, suitable storage, protected routes, source timestamps, and user-visible reconciliation before being called live. Avoid deploying placeholders as if they were actual performance results.
