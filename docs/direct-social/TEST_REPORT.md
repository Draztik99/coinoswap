# CoinoSwap Direct Social — Shadow Test Report
**Date:** 2026-11-23 (Africa/Johannesburg)
**Tested source commit:** `c3c427e00f904c885b8511ee412e3ff4e2dc7d08`
**Branch:** `feature/direct-social-publishing`
**Test run:** https://github.com/Draztik99/coinoswap/actions/runs/45239074763
**Result:** **95 tests passed**; syntax checks, offline safety tests, and blank dashboard artifact upload passed.
**Classification:** Development/SHADOW ONLY. No live publishing, API login, token read, Metricool mutation or production migration.

## Verified tests and capabilities
- Official CoinoSwap 2026-11-23 BTC/ETH/XMR JSON/PNG pair validates against real archived SHA-256, source quotations and original SAST publishing time. Its reuse on a later date is blocked.
- Price freshness, source deviation, wrong day, corrupt file, tampered image, invalid price and expired target window trigger fail-closed behavior.
- Existing 1536×1024 official PNG is unchanged. It is within X's 5MB PNG limit and FB's 10MB photo limit; a separate Instagram-compatible full-size JPEG is generated in memory with its own SHA-256. Tests compare JPEG against original pixels and check repeatability.
- Offline X request contracts cover media upload (`tweet_image`), post creation, receipt checks and conservative caption limits. No X account was contacted.
- Offline Meta request contracts cover Facebook Page photo, Instagram HTTPS image URL, media-container status, publish and verification GET. No Meta account was contacted.
- Simulated 15-way concurrent send attempts reserve exactly one platform/day/campaign slot in local SQLite. Timeout, 401, 429, 500 and missing-receipt outcomes are marked UNKNOWN and blocked from blind retries.
- A simulated independently verified Metricool FB/IG publication record reserves the same day/campaign and blocks a duplicate direct send.
- A release gate blocks all live integration by default. FB/IG are blocked while Metricool remains active, even with hypothetical credentials.
- Analytics normalizer preserves missing metrics as `N/A`, separates views from impressions, avoids double-counting reposts/shares and attributes completed swaps only to exact tracked sessions with verified backend transaction IDs.
- An offline black-and-gold HTML dashboard is generated with **no fabricated data**; no website, social or swap backend is connected. It is downloadable from the test run's Artifacts area.
- Failure-alert payloads are constructed and secrets are redacted; no email, Telegram, or webhook delivery is active.
- Static safety checks ensure no social request transport was introduced in the shadow code.

## Production integrity
- Production `main` remains at commit `2527f998141af9d5fd7f8a0e375474935a0f1a2a`, not altered by this work.
- No pre-existing `.github/workflows/daily-rates*.yml`, `daily-rates/`, `docs/daily-rates/` or external Metricool publishing automation was edited.
- Only a new branch-specific, read-only GitHub Actions test workflow exists for direct social. It is not a publishing scheduler.
- The `main` branch is not protected according to GitHub's read-only branch metadata; a PR-protection ruleset should be arranged before eventual merge.

## Remaining true integration prerequisites
**X:** Developer app and billing/access; OAuth 2.0 user authorization/scopes `tweet.read`, `tweet.write`, `users.read`, `media.write`, `offline.access`; secure server-side redirect/callback and token storage. No credentials should be committed or pasted into chat.

**Meta:** Business developer app, accessible Facebook Page, linked Instagram Professional account, Page/IG role approvals, supported access tokens, appropriate `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `instagram_basic`, `instagram_content_publish` permissions (depending on login model). Instagram requires publicly reachable JPEG; conversion is tested, hosting is not configured.

**Infrastructure:** Shared durable authoritative database with atomic constraints (local SQLite prototype is NOT safe across ephemeral independent GitHub runners), secure secret manager, deployment/run target, cross-publisher reconciliation and live alert destination.

**Measurement:** Actual CoinoSwap website visit/session events and backend-verified completed swaps with duplicate-safe transaction IDs and consent/retention policy. No actual website or completed-swap data is presently connected to the dashboard.

**Release:** Production approval, X first at exactly one post per SAST date, several days of verified receipts, then separate explicit Meta cutover approval. Existing Metricool automations remain in place until approved.

## References used (verified 2026-11-23)
- X create post: https://docs.x.com/x-api/posts/create-post
- X upload media (PNG/JPG/GIF/WEBP, tweet_image <=5MB): https://docs.x.com/x-api/media/upload-media
- X OAuth 2.0 authorization code flow: https://docs.x.com/fundamentals/authentication/oauth-2-0/user-access-token
- Meta Facebook Page Photos: https://developers.facebook.com/docs/graph-api/reference/page/photos/
- Meta Instagram content publishing (public server and JPEG): https://developers.facebook.com/documentation/instagram-platform/content-publishing
