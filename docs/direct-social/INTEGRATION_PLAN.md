# CoinoSwap — Direct Social Publishing Integration Plan

**Date:** 2026-11-23 (Africa/Johannesburg)
**Branch:** `feature/direct-social-publishing`
**Production source:** `main` (unchanged)
**Status:** ARCHITECTURE / PLAN ONLY. No direct publisher implemented or enabled.
**Safety contract:** Never alter the existing Metricool automations, production GitHub workflows, assets, or credentials without a separate approval. No live X, Facebook, or Instagram calls during development.

## A. Verified source architecture (read-only audit)
- Repository `Draztik99/coinoswap` is public; default branch is `main`.
- `.github/workflows/daily-rates.yml` generates assets only. It schedules preparation around seven randomized SAST daily slots and accepts emergency workflow dispatch.
- `.github/workflows/daily-rates-slot-tests.yml` verifies randomized slot logic (no posting); `.github/workflows/daily-rates-sunday-test.yml` is a one-off generate-only path.
- `daily-rates/prepare_rates.py` validates CoinMarketCap + Kraken BTC, ETH, XMR prices, freshness, source deviations (BTC/ETH 1%, XMR 2%) and duplicate *assets*. It generates `docs/daily-rates/YYYY-MM-DD.{png,json}` with image SHA-256.
- `daily-rates/render_rates.py` renders an approved 1536×1024 PNG. Instagram may need its own approved JPEG derivative; keep the source image unchanged and hash any derivative separately.
- The output audit is marked `VALIDATED` and `NOT_PUBLISHED`; publishing is outside this repository through ChatGPT–Metricool.
- **Independent read-only Metricool check (2026-11-23):** CoinoSwap brand has Facebook, Instagram and YouTube connected; X was not listed on this brand. Metricool's planner reported the 2026-11-23 14:49 SAST Daily Rates post as **PUBLISHED** to both Facebook and Instagram, with public URLs. The GitHub audit's `NOT_PUBLISHED` state is not a contradiction: it tracks generation only. No scheduled content or automation was changed. These observations are a snapshot, not proof that future automated runs will succeed.
- No direct social posting adapters, cross-platform idempotency ledger, social metrics collector, or website/swap attribution code exists in this repository.
- The `daily-rates/README.md` describes an older fixed slot and should be corrected in a future reviewed PR, not as part of this isolation phase.
- The default branch was shown as unprotected in the GitHub branch listing; confirm rulesets separately before rollout.
- One 2026-11-23 manual generation run failed during asset generation; its precise exception has not been confirmed. Successful runs also exist, and the 2026-11-23 audit asset is validated. Do not interpret a generator failure as a social publishing failure.

## B. Proposed components and boundaries
```
MAIN (existing, unchanged):
  CoinMarketCap + Kraken -> validate -> approved PNG + JSON in docs/daily-rates/
  ChatGPT–Metricool watcher/publisher (existing, unchanged)

FEATURE BRANCH (no live posting):
  Source reader (pin main commit/ref; verify audit, SHA, date, freshness)
       -> platform-specific packaging (X PNG, FB PNG, IG JPEG derivative)
       -> queue/ledger (durable at-most-once per platform per SAST date/campaign)
       -> platform adapters (X / Meta Facebook Page / Meta Instagram Professional)
       -> post receipts + reconcilers
       -> metrics collectors + first-party website/swap events
       -> dashboard + alerting
```
Keep new code under `social-publisher/`, tests under `social-publisher/tests/`, and later a **separate** workflow named e.g. `.github/workflows/direct-social-publisher.yml`. Do not edit existing YAML in this branch.

## C. Step-by-step implementation

### Phase 0 — Establish safety and access (read-only)
1. Preserve current `main` SHA, workflow inventory, recent successful/failed actions run IDs, image SHA, and existing Metricool publication schedule.
2. Use `feature/direct-social-publishing` only. No merge to `main`; no production credentials on this branch.
3. Confirm X Developer access/credit balance, X account OAuth scopes, Meta developer app/business portfolio/Page/Instagram Professional account, app permissions, and existing website analytics/backend swap completion event source. Do not paste tokens into chat or Git.
4. Choose a durable store and deployment target. Prefer managed PostgreSQL for cross-run atomic idempotency; SQLite works only with durable, single-worker hosting, not ephemeral independent GitHub runners.

### Phase 1 — Build and test ingestion (no social network calls)
5. Build `asset_reader`: read main's validated JSON + image at a pinned commit; require `status=VALIDATED`, matching SAST day, exact SHA-256, BTC/ETH/XMR data, source timestamps/deviation caps, and publication cutoff. Reject stale, partial or inconsistent pairs. Do NOT interpret JSON `approval_state` as a social publication receipt.
6. Build `post_composer`: platform-specific text, URL/UTM, asset format and caption validation. Keep official design intact; convert JPEG for Instagram only if necessary and verify visual fidelity. Instagram caption URLs are generally not clickable: plan a tagged profile/bio landing link for Instagram traffic.
7. Test edge cases: stale prices, missing JSON, hash mismatch, prior-day asset, late runner, duplicate date, partial failure, malformed/unsupported media, incorrect approval state, timezone boundary. No external post calls.
8. Keep an explicit `PUBLISH_ENABLED=false` default **and** require an approved production deployment environment; a config flag alone is not a sufficient interlock.

### Phase 2 — Durable publication state and safety
9. Create publication ledger keyed by `(platform, date_sast, campaign_key)` with a database UNIQUE constraint, plus `asset_sha`, intended_time, provider_post_id, request_id, attempts, timestamps, and lifecycle states `READY / RESERVED / SENDING / PUBLISHED / UNKNOWN / FAILED / SKIPPED_STALE`.
10. Lock each platform-date job transactionally before attempting an API request; serialize processing and use a unique CI/workflow concurrency group. Rate limit with backoff. Do not blindly retry a network timeout after a possibly accepted publish—mark `UNKNOWN` and reconcile platform feeds/post IDs first.
11. Persist provider receipt IDs and canonical post URLs; independently verify post existence. A successful upload/container creation alone is **not** a published post.
12. During the overlap period, track externally published Metricool posts too. Until an authoritative cross-publisher lock/schedule is available, keep direct Facebook/Instagram LIVE disabled while Metricool posts those platforms. A hard cutover is a separately approved operation.

### Phase 3 — API adapters
13. X: obtain user-authorized OAuth credentials, upload media to X, then create a post referencing the media ID; save ID and receipt. Start with exactly one scheduled X post per SAST day, initially in test mode. Validate X API billing, media requirements and read/analytics permissions against the account's actual tier.
14. Facebook: Meta Facebook Login for Business / Page access with `pages_show_list`, `pages_manage_posts`, `pages_read_engagement` as applicable. Publish image+caption via Page Photos/Feed, capture post ID, verify appearance. Do not use a personal timeline.
15. Instagram: use linked Instagram Professional account. With Facebook Login, confirm `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights` and relevant Page permissions; with Instagram Login the host/scopes differ. Create media container from publicly reachable image URL, poll processing status, publish via `/media_publish`, verify media ID/permalink. Never publish test content on the brand account without explicit approval.
16. Authenticate through restricted production environment/secrets; minimum scopes, encrypted rotation, revoked-token alerts, and redaction of all headers/tokens in logs. Separate test and production app credentials.

### Phase 4 — Analytics and conversion measurement
17. Persist daily per-post metrics where APIs permit: views/impressions (label platform-specific metric), likes/reactions, comments, shares/reposts, link clicks and engagement rate. Mark unsupported metrics `N/A`, not zero. Meta has deprecated several older impression metrics, so query the currently supported API version.
18. Use first-party UTM links for X/Facebook (e.g. `utm_source=x&utm_medium=organic_social&utm_campaign=daily_rates&utm_content=2026-11-23`), and an Instagram profile/bio redirect with campaign attribution. Store click/visit/session events, with consent/privacy controls.
19. Integrate verified **completed swap** events from CoinoSwap's backend / partner status system, keyed by unique transaction ID (no double counting). Map source session -> swap when attributable; report unattributed separately. Keep financial amount, completed count, conversion rate and optionally confirmed fees distinct.
20. Provide dashboard: publishing status by platform/day; 7/30/90-day impressions or views; engagements; tracked website sessions; completed swaps; USD volume; conversion funnel; cost by API; errors. Include event timestamps and source freshness.

### Phase 5 — Testing, alerts, review and staged launch
21. Add mock-provider unit tests, contract tests, forced 429/401/timeout/5xx tests, network interruptions, repeated job invocation, cross-process collision tests and a 7-day shadow run (read/validate/log only). All should prove **zero** live posts in shadow mode.
22. Add alerts for validation failure, expired asset, token expiry, permissions, failed/unknown post, 429/rate limits, missing daily receipt after cutoff, and analytics lag. Alert should include platform, date, failure reason, retry state, link to run, but no token.
23. Confirm launch readiness: X billing funded, app permissions granted, tested media uploads, durable DB, secret rotation, verified post/receipt, alert delivery, dashboard sanity, explicit approvals.
24. Go-live sequence: (a) approve X direct 1/day; (b) verify several days of single-post X receipts; (c) approve **per-platform** Facebook/Instagram cutover only after Metricool handoff can avoid duplication; (d) keep Metricool intact until that approval. No silent cutover and no parallel LIVE publishers for the same platform/campaign.
25. After approval only, release reviewed workflow to default branch and enable scheduler, with hard kill switch and rollback to Metricool if needed.

## D. GitHub Actions constraint
GitHub `schedule` triggers only from workflow files on the **default branch**. A feature-branch scheduled YAML cannot execute independently through regular `schedule`. During isolated development use local CI tests or a feature-branch-only `push` test workflow that cannot access live publishing secrets. Do not add production `schedule` on `main` before explicit approval.

## E. Open prerequisites, not yet verified
- X developer app ID, OAuth grant permissions, available pay-per-use credit and separate media/metric costs.
- Meta app/Business Portfolio, Facebook Page ID, linked Instagram Professional ID and granted permissions/app review status.
- Whether direct post media format should preserve today's 1536×1024 size on both FB/IG.
- CoinoSwap website analytics stack and backend's canonical `swap_completed` event.
- Preferred durable DB/hosting and alert recipient/channel.
- Confirm Metricool's actual posting schedule and reconciliation method at the moment of platform cutover.

## F. Release acceptance criteria
- Metricool unchanged and operating during development.
- No secrets committed or exposed in logs; default branch and prod environments protected.
- One and only one confirmed X post per SAST date after separate live approval.
- FB/IG confirmed receipts only after each platform's approved cutover; no duplicate alongside Metricool.
- Fail-closed on stale/invalid assets, at-most-once behavior under retries/timeouts, visible UNKNOWN reconciliation.
- Dashboard shows API metrics with definitions/availability, tracked web visits and verified completed swaps, without invented attribution.
- Failure notification reaches configured destination; rollback documented and tested.

## Authoritative references checked 2026-11-23
- X Developer pricing and access: https://developer.twitter.com/
- X posting/media overview: https://github.com/xdevplatform/docs/blob/main/x-api/posts/manage-tweets/introduction.mdx
- Facebook Page Photos: https://developers.facebook.com/docs/graph-api/reference/page/photos/
- Instagram media container/publish: https://developers.facebook.com/docs/graph-api/reference/shadow-ig-user/media/
- Meta Page Insights and deprecated metrics: https://developers.facebook.com/docs/graph-api/reference/insights/
- GitHub scheduled workflow default-branch behavior: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
