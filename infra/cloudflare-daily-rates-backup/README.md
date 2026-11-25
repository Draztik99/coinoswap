# CoinoSwap Daily Rates — Independent Cloudflare Cron backup

**Deployment status: NOT ACTIVE until Cloudflare Worker is deployed and the secret installed.**
The main GitHub scheduled workflow remains active/configured as primary. The backup only asks GitHub to perform the **existing** randomized-slot preparation, immutable source validation, Facebook duplicate reservation and single verified post. This Worker itself cannot POST to Facebook and has no social credentials.

## Why

On 25 November 2026, scheduled GitHub cron events for Daily Rates were not recorded for the selected slot; the approved manual rescue was eventually published with a fresh image and verified Meta receipt. GitHub scheduled jobs are best-effort, so prepare a second scheduler on Cloudflare. Cron uses UTC; SAST = UTC+2 year-round.

## Guardrails

- The Worker accepts **only Cloudflare Cron** events; direct web access returns HTTP 404.
- 14 dispatch opportunities: 9 and 4 minutes before each of the seven SAST slots (11:30, 12:00, 12:30, 13:00, 13:30, 14:00, 14:30). The GitHub randomized selection picks **one** actual daily slot, rejects all other slots and treats duplicate sources as no-ops.
- `workflow_dispatch` inputs are `emergency=false`, `backup_trigger=true`; normal manual runs default to `emergency=true`, `backup_trigger=false` and **do not publish**.
- GitHub preserves the 15-minute prewarm gate and original strict 4-minute quote collection window; stale quotes, a missing validated image, a duplicate tag or failed Meta identity/readback block publication. Backup dispatch never bypasses the Facebook pause variable.
- The same GitHub concurrency group serializes primary and backup; the source commit is immutable, and there is no retry after an uncertain Meta POST.
- Cloudflare and GitHub do **not** get access to each other's Page token, Metricool settings or API credentials. The Worker needs only the scoped GitHub Actions dispatch credential.

## Deploy (requires authorized Cloudflare and GitHub account setup)

1. Create a **fine-grained GitHub PAT** for only `Draztik99/coinoswap`, with repository permission **Actions: Read and write** and no other write permissions. Prefer an organization-approved GitHub App token for long-term rotation; protect its expiration.
2. In Cloudflare Workers, deploy from this directory with `npx wrangler deploy` (Wrangler authentication required). Alternatively create the Worker in the Cloudflare dashboard and configure the exact source code and schedules shown in `wrangler.toml`. Do not add a public route.
3. Securely add Worker secret `GITHUB_ACTIONS_TOKEN` (e.g., run `npx wrangler secret put GITHUB_ACTIONS_TOKEN` inside this directory). Do not put its value in GitHub files, logs, dashboards or chat.
4. Verify the Worker displays BOTH UTC cron expressions `21,26,51,56 9-11 * * *` and `21,26 12 * * *`. Cloudflare cron changes can take several minutes to propagate.
5. Confirm GitHub `.github/workflows/daily-rates.yml` remains enabled, `COINOSWAP_FB_DAILY_PAUSED` is not `true`, the `facebook-live` Page secret still authenticates, and Metricool Facebook publishing remains disabled. Do not change the Instagram automation.
6. Test the Worker with a mocked fetch using `node --test src/index.test.mjs`. Inspect the first live Cron invocation log for `DISPATCH_ACCEPTED_NOT_PUBLISHED`; **that only proves GitHub accepted the workflow request**, not a Facebook publication.
7. Inspect the GitHub run for a `workflow_dispatch` backup, check validated fresh source, and require a `META_PAGE_PHOTO_READBACK` publication receipt to count actual delivery. Never rerun an uncertain Meta POST.

## Operation and failure response

- If GitHub rejects dispatch with 401/403, rotate only the Cloudflare `GITHUB_ACTIONS_TOKEN`; this is not the Facebook Page token.
- If the GitHub workflow starts but selection skips, it was not the randomized day's chosen time, or the daily source was already created; this is an expected no-op.
- If fresh generation or Meta verification fails, alert and inspect the specific stage. Do not retry the entire posting workflow when outcome is uncertain.
- Keep the original GitHub daily verification alarm and read-only analytics collector. No browser route can trigger posting.
- On the free plan, review Cloudflare Worker invocation quota and GitHub Actions usage; this backup runs at most 14 dispatch requests per day, most of which are harmless no-ops.

## Reference

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
