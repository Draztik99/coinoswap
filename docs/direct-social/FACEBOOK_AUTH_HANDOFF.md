# CoinoSwap Facebook-only API handoff (development, no posting)

**Date:** 2026-11-24 (SAST)  
**Branch:** `feature/direct-social-publishing`  
**Production:** `main` and all Metricool schedules unchanged.

## Verified manually in Meta Graph API Explorer

- Meta app: `CoinoSwap Social Publisher`.
- CoinoSwap Facebook Page: `108130358772133`.
- User authorization succeeded with requested scopes: `pages_manage_posts`, `pages_show_list`, `pages_read_engagement`, `read_insights`.
- `GET /me/accounts?fields=id,name,tasks,access_token` returned the expected Page, a Page token, and the `CREATE_CONTENT` Page task (confirmed by owner; no secret saved).
- With **Coinoswap** selected under **User or Page**, `GET /me?fields=id,name` returned Page ID `108130358772133` and name `Coinoswap`. This confirms **Page-token identity** only; it is not a live publishing verification.
- Instagram on hold due to linking/security and business portfolio limitations.

## Security and launch constraints

1. Do **not** paste access tokens, app secrets, OAuth codes or full `/me/accounts` responses in chat, issues, commits or logs.
2. Explorer-generated credentials are for exploration, not automatically suitable for an unattended scheduler. Before live use, confirm token validity, expiry/invalidation conditions and applicable app mode; plan scoped storage and rotation.
3. Store tokens only in a reviewed secret manager or dedicated environment-scoped deployment secret **after** choosing a production deployment strategy. Never put secrets in source code or a general workflow environment.
4. Only execute **read-only GETs** while Metricool is active; direct Facebook POSTs remain disabled until explicit Facebook-only authorization and a duplicate-safe handoff.
5. Validate the account identity with `/me?fields=id,name`; ensure the result is exactly the CoinoSwap Page ID. Check Page tasks and app permissions independently.
6. Ensure durable idempotency, time-window validation, external Metricool receipt reconciliation, post-existence verification, alerting and rollback before any live cutover.
7. Keep this branch's `direct-social-tests.yml` strictly offline. No permissions that write to Facebook and no action schedules are added.

## Current code

- `social-publisher/facebook_page_auth.py`: pure, network-free request specifications and secret-free verification of Page identity and Page tasks.
- `social-publisher/tests/test_facebook_page_auth.py`: offline unit tests for correct/wrong Page identity, missing permissions and token non-disclosure.
- `social-publisher/launch_gate.py`: blocks Facebook live integration while Metricool is active.

## Next engineering phase (requires separate approval for any external operation)

Implement a **GET-only credential health probe** with environment-injected secrets, no token logging, explicit allowlisted Meta Graph URL, timeout and safe redacted errors; verify locally or in an isolated reviewed environment. Never enable live social POST from this diagnostic.

## 2026-11-24 — Credential health implementation (manual GET-only)

- New `social-publisher/facebook_health.py`: explicit command-line `--check` performs one fixed read-only HTTPS request to Meta's `/me?fields=id,name`, using a Bearer token only from `COINOSWAP_FB_PAGE_ACCESS_TOKEN` in process environment.
- Fixed URL, TLS verification, disabled redirect following, 8-second default timeout, 16 KiB maximum response, safe status classifications and no raw provider errors or token values in printed output.
- New offline mocked tests cover identity, missing/malformed credentials, token nondisclosure, wrong Page, malformed data, oversize response, 3xx/4xx/429/5xx and network failures. No credentials are configured or run in CI.
- Code being committed is **not** evidence of a successful live credential-health request. The earlier owner-run Graph API Explorer test already confirmed current Page identity.
- These changes do not establish production secrets, refresh/expiry management, scheduling, post publication or cutover approval; those remain separate gated work.
