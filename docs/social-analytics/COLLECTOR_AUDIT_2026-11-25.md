# CoinoSwap social analytics collection audit — 2026-11-25 (SAST)

**Status:** Source-code audit and read-only test additions. This is not a live Graph API performance claim.

## Verified by inspecting repository source

### Facebook (separate from Metricool)
- `social-publisher/insights/facebook_collector.py` retrieves only verified CoinoSwap Page photo publication receipts.
- GET requests are limited to Meta Graph identity, verified post/photo readback, optional interaction counts, and optional `post_media_view` insights.
- A fallback for photo-backed Page stories may retrieve only partial metrics. Unsupported/denied insights remain null (N/A), not zero.
- **Reach is not currently retrieved by the Facebook collector at all.** The `model.facebook_post_snapshot` mapping assigns reactions/comments/shares, derived interactions and optional views; it never sets reach. The dashboard's Facebook reach N/A is therefore consistent with the code, not necessarily a credential failure.
- Exactly one immutable snapshot can be saved per publication per SAST collection date. Re-running the same date skips the existing file and does not refresh that day's data. It is possible for later collections to update the latest snapshot on subsequent dates.
- Receipts older than 32 days are excluded from active collection (but existing snapshots remain in history).
- A validated Page token is required. Token failure is surfaced as a workflow failure after existing reports are retained, rather than authorizing any Facebook publishing.
- Coverage instrumentation was fixed in this change: `posts_eligible` now counts all current-window eligible receipts, independent of whether a dated snapshot already exists. The collector separately returns `snapshots_already_present`, `receipts_outside_collection_window`, and `collection_window_days`.

### Instagram via Metricool
- The Metricool professional Instagram account is connected according to the user's Metricool UI, but Facebook is intentionally disconnected to avoid changing existing Instagram-only publishing restrictions.
- `instagram_inbox.py` does **offline** conversion of files already in `docs/social-analytics/inbox/instagram`. The GitHub collector workflow does **not** call Metricool API by itself. Without an external ingestion step, new Instagram metrics will not automatically arrive.
- The importer validates the brand ID, exact fields, dated filename, source timestamp, and existing immutable output. It also filters for CoinoSwap Daily Rates caption signatures; it should not be represented as a complete history of all Instagram posts.
- The connected Metricool analytics query returned zero rows in earlier checks despite one post shown in the UI. This requires provider-side verification; the screenshot proves a UI record, not the correctness of the API's reporting response.
- Free-plan historic reporting restrictions are visible in the Metricool interface. No plan upgrade is authorized by this audit.

## Important reporting caveats
- Counts are coverage **within tracked/verified sources**, not proof of the total number of posts across every social platform.
- Avoid inferring engagement rate, CTR, or post reach where corresponding denominators are absent.
- A current build timestamp does not guarantee a current source snapshot.
- No changes to Facebook posting, scheduled Instagram posts, Cloudflare Access, data persistence permissions or social account connections are required for this audit.

## Next safe engineering steps
1. Run full offline unit tests and ensure GitHub CI reports success.
2. Inspect the Meta collector's next authorized GET-only run and compare safe status counts; never print the token or raw provider response.
3. Investigate whether an approved *post-level reach* metric is available for the exact supported Graph object and permissions. Add it only after a proven mock/provider contract and null-handling tests; do **not** invent Facebook reach from views.
4. Design a secure read-only Metricool-to-inbox transfer that does not depend on ChatGPT conversation actions, and never grants the publishing automation new permissions.
5. Confirm Cloudflare Access blocks `/reports/post-performance.csv` for unauthorized identities and that preview deployment hashes remain protected.
6. Avoid adding private search queries, customer records or swaps to this **public GitHub repository**.
