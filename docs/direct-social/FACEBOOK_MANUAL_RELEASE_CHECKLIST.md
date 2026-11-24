# CoinoSwap — Facebook manual release checklist (NO GO until complete)

**Scope:** Page 108130358772133, official BTC/ETH/XMR Daily Rates only.

## Deployed and verified
- GitHub generator reliability fix PR #3 merged to main (24 Nov 2026).
- No actual Facebook or Instagram posts sent by the direct system.
- Manual sender **code** staged in `feature/direct-social-publishing`; manual workflow is not active on main.
- All development tests must pass, including isolated unit tests for the live sender with fake Meta responses and fake Git subprocess calls.

## Missing operational prerequisites
1. Obtain an appropriate authorized long-term CoinoSwap Facebook Page token and review expiry/invalidations and app mode. Never paste it into ChatGPT, commits, issue comments, logs, scripts or screenshots.
2. After approval to deploy the manual sender code, create GitHub **Settings → Environments → facebook-live**, configure required reviewer protection where supported, and put `COINOSWAP_FB_PAGE_ACCESS_TOKEN` in that environment as a **secret**, not a variable.
3. Set GitHub environment variables `COINOSWAP_FB_LIVE_ENABLED=true` only for a specifically approved single-post test, and `COINOSWAP_METRICOOL_FB_DISABLED=confirmed` only *after* disabling overlapping **Facebook** delivery in BOTH external CoinoSwap Rates automations; keep Instagram on Metricool.
4. The selected day's official `main` image and audit must actually be present, validated, and inside the allowed SAST publication window. GitHub scheduled Actions are best effort; do not override stale-quote limits or post yesterday's image.
5. Review existing Facebook published posts and Metricool state to ensure today's campaign was not already posted. The script also checks for probable duplicates, but negative Meta results alone are not authoritative.
6. Only then, explicitly run the **manual** workflow on `main`, entering `I_APPROVE_SINGLE_COINOSWAP_FB_POST`. Running it twice can never produce two posts: the first makes an append-only Git reservation before a POST.
7. Verify the resulting Page post and public permalink; if outcome `UNKNOWN`, **do not retry or delete the reservation tag**. Reconcile manually in Facebook and GitHub.
8. After a proven manual post, separately assess daily scheduling, rate freshness, ongoing Meta credential monitoring, failed-post alerts, backup and rollback. Do not remove Metricool Instagram.

## Security architecture
- No workflow in this development branch can access Facebook secrets; `direct-social-tests.yml` has only repository read permission and mocked requests.
- The manual workflow has no `schedule`, `push` or `pull_request` trigger; its job is restricted to `refs/heads/main`.
- Only an explicit approval phrase, protected production environment, Page secret, disabled-Metricool declaration and immutable image can start a send.
- Single fixed URL `https://graph.facebook.com/v27.0/108130358772133/photos`; bearer token appears only in HTTP Authorization header.
- GitHub tag reservations: `coinoswap-facebook-daily-rates-YYYY-MM-DD` are append-only. Existing tags prevent duplicate sends.
- The Meta POST is never retried, including on timeout; unknown outcomes need manual review.

## Current decision
**NO GO for live direct Facebook publishing** until all missing prerequisites are independently confirmed. The production generator repair improves reliability but still requires observation at the next real scheduled slot.
