# CoinoSwap — Facebook-only deployment readiness / handoff

**Updated:** 2026-11-24 (Africa/Johannesburg)
**Scope:** Facebook Page `108130358772133` ONLY.
**Repository:** `Draztik99/coinoswap`, development branch `feature/direct-social-publishing`.
**Production:** Default branch `main`, existing Daily Rates workflows and external Metricool automations remain unchanged.
**Current mode:** SHADOW / GET-ONLY. **Zero Facebook publishing capability activated.**

## What has been verified

1. Meta Developer app `CoinoSwap Social Publisher` successfully authenticates.
2. In Graph API Explorer, Page token `GET /me?fields=id,name` returned Page `Coinoswap` and ID `108130358772133`.
3. `/me/accounts?fields=id,name,tasks,access_token` returned a Page access token and task `CREATE_CONTENT` (manual confirmation; never saved to GitHub).
4. Scopes requested in Graph API Explorer: `pages_manage_posts`, `pages_show_list`, `pages_read_engagement`, `read_insights`.
5. Metricool brand 8283300 reported Facebook Page `108130358772133` and Instagram `coinoswap` connected in its read-only brand settings on 2026-11-24.
6. Metricool scheduled-post query for 2026-11-24 through 2026-12-01 returned no planner entries. This says **nothing** about future ChatGPT automations, already published posts, or posts outside the query's visibility.
7. On 2026-11-24, **168 offline safety tests and 6 real PostgreSQL 16 integration tests passed** on the feature branch (GitHub Actions run 45425702471). The PostgreSQL instance was disposable and is not a deployment.
8. The feature-only CI workflow was updated to checkout v6, setup-python v6, upload-artifact v6 (Node.js 24-compatible), with a policy test prohibiting production schedules, social credentials, and write-permission grants.

## Facebook development components

| File | Purpose | Network |
| --- | --- | --- |
| `facebook_page_auth.py` | Page identity / tasks validation | none |
| `facebook_health.py` | Explicit manual Page token identity check | one fixed Meta GET |
| `facebook_shadow.py` | Validate pinned main-branch asset + build inert Facebook photo request plan | pinned GitHub GET only |
| `facebook_reconciliation.py` | Parse Meta published-post response, flag potential duplicates | none |
| `facebook_page_readback.py` | Explicit manual Page identity + published-post audit | two fixed Meta GET requests |
| `facebook_token_review.py` | Offline review of token validity, app identity, scopes and expiry metadata | none |
| `pg_ledger.py` / `postgres_schema.sql` | Atomic PostgreSQL reservation / reconciliation, tested in disposable DB | no social network |
| `contracts.py` / `receipts.py` | Inert photo POST contract / verified post receipt schema | none |
| `launch_gate.py` / `ledger.py` | Block live while Metricool active and persist simulated idempotency | local offline SQLite |
| `.github/workflows/direct-social-tests.yml` | Offline unit tests, real disposable PostgreSQL service, dashboard on feature branch | no Meta or Metricool calls |

**Important:** A Page published-post readback that finds no matching caption is *not* proof there are no Metricool posts. Photo-only posts, incomplete pagination, app permissions, and separate publishing automations require independent reconciliation. This system has no mechanism for posting in production.

## Safe manual read-only diagnostics (not scheduled)

Use **only** an isolated trusted local shell/session with a Page token securely provisioned via its process environment as `COINOSWAP_FB_PAGE_ACCESS_TOKEN`. Never put the token in command arguments, command history, screenshots, issue comments, chat, repository files or Actions variables on the public feature branch.

```sh
python social-publisher/facebook_health.py --check
python social-publisher/facebook_page_readback.py --check
```

Without the secret, both commands safely report `NOT_CONFIGURED`. Neither calls Facebook with POST; there is no automatic retry, redirect-follow or scheduling. Raw provider payloads/errors and tokens are never printed.

Shadow asset audit (requires a specific approved main-branch commit containing today's validated Daily Rates JSON/PNG pair):

```sh
python social-publisher/facebook_shadow.py --commit-sha <IMMUTABLE_MAIN_COMMIT_SHA>
```

This command can fail closed on expired assets or an unavailable pinned pair. A valid response always says `BLOCKED_METRICOOL`, and the post count remains zero. It does not activate the inert POST request contract.

## Still required before any production direct Facebook publishing

1. **Production token architecture**: choose authorized token type and review expiration/invalidation, refresh and rotation; record Meta app mode, authorized Page tasks and relevant permissions. Explorer tokens alone are not production credential management. A Meta system-user token requires correct Business portfolio/app/Page relationships and authorizations; availability is **not yet proven**.
2. **Credentials in a restricted environment**: dedicated secrets manager or GitHub Actions production environment with reviewer protections; never store in source, logs or pull-request jobs. Do not wire secrets into this feature branch's CI.
3. **Durable idempotency store**: PostgreSQL (or equivalent) with one atomic UNIQUE key `(platform, date_sast, campaign_key)`; the PostgreSQL prototype has passed real disposable-container tests but **is not provisioned in a production environment**.
4. **Cross-publisher reconciliation**: authoritative checks of Metricool post state plus Facebook published post readback, before and after each attempted post; stale/missing/ambiguous API results must BLOCK. No blind resend on timeout.
5. **Real sender adapter**: separately reviewed code using Page `POST /{page-id}/photos` and separate GET verification. Must be fully disconnected/disabled until live approval and cutover, with a hard kill switch and monitored alerts.
6. **Release process**: at least seven clean shadow days, token validity monitoring, error injection (400/401/403/429/500/timeouts), DB collision tests, complete audits/receipts and rollback rehearsal.
7. **Managed ledger deployment**: migrate `social-publisher/postgres_schema.sql` to an authorized database; inject DB connections into `pg_ledger.py` on a secure worker; prove transactional collisions using a real PostgreSQL integration test. The earlier fake DB tests were supplemented with six real disposable PostgreSQL tests; **managed deployment and production concurrency checks remain outstanding**.
8. **Explicit Facebook-only cutover approval**: remove Metricool as *live Facebook campaign publisher* only after the replacement is ready; preserve Instagram via Metricool. Prevent duplicate schedule overlap.
9. **No Instagram or X changes** as part of Facebook-only scope.

## Security & operational design decisions

- Default **NO LIVE POST**. Do not create or enable a production workflow or scheduler on `main`.
- Current shadow and readback paths are explicit GET or pure code only, with TLS checking and closed redirect handling.
- Graph API endpoints are pinned to v27.0 and the verified CoinoSwap Page ID. Do not accept arbitrary Page IDs, external hosts or token-bearing URLs.
- If any request's outcome is uncertain, record `UNKNOWN`, do not retry automatically, and reconcile on Facebook before deciding.
- Warn that meta-app development/testing permissions may not automatically grant public production publishing. Verify app review/business verification requirements with Meta, using current account configuration.
- Keep actual source SHA-256 and published Post ID/permalink and a stable attribution key in receipts; no inventing impressions, swap counts or conversions.

## References

- Meta Page Photos API: https://developers.facebook.com/docs/graph-api/reference/page/photos/
- Meta Page Published Posts read API: https://developers.facebook.com/docs/graph-api/reference/page/published_posts
- Meta system-user tokens: https://developers.facebook.com/docs/business-management-apis/system-users/install-apps-and-generate-tokens/
- GitHub environment approvals: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments

**Status classification:** Engineering work is safe to continue on feature branch. Live API posting is not authorized or configured and cannot responsibly be claimed complete.

## 2026-11-24 — Manual single-post transport prototype

- The production `main` branch source-generator reliability fix was merged separately via [PR #3](https://github.com/Draztik99/coinoswap/pull/3); it changes source retries/monitoring but sends NO social posts.
- Staged manual sender: `social-publisher/live/facebook_once.py` + `publish_cli.py` + `tag_ledger.py`.
- The isolated `.github/workflows/facebook-manual-publish.yml` exists only in development until an approved merge. It has **workflow_dispatch only, no schedule** and only starts on main after typing the single-post approval phrase and meeting environment requirements.
- Rather than requiring a managed PostgreSQL database for one serial manual publisher, it uses an **append-only Git tag per SAST date** as the durable reservation before the Meta POST. A duplicate or uncertain reservation blocks a second attempt. Do not force-update/delete tags to reset an UNKNOWN delivery.
- Private `COINOSWAP_FB_PAGE_ACCESS_TOKEN`, `COINOSWAP_FB_LIVE_ENABLED=true` and `COINOSWAP_METRICOOL_FB_DISABLED=confirmed` are required in a protected `facebook-live` environment. They are **not configured** and none are injected into development CI.
- Source is a pinned, current-day, checksum-validated BTC/ETH/XMR PNG and audit; Page identity and positive duplicate detection run via read-only GET before reservation. Only one POST to the fixed CoinoSwap Page photo endpoint is attempted, followed by readback. Unknown outcome requires manual reconciliation, never automatic resend.
- The Meta Page token, app live-mode status, long-term validity, production environment, Metricool cutover and a live authorized test remain **unverified**. **DO NOT PUBLISH** based on this code alone. It is code readiness, not production approval.
- This manual proof-of-publication path does not automatically schedule or publish every day's rates. A future always-on scheduler requires a separately approved cutover and more observation.
- Exact operator handoff: `docs/direct-social/FACEBOOK_MANUAL_RELEASE_CHECKLIST.md`.
