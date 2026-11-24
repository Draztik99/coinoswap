# CoinoSwap Meta Page Token Recovery — 24 November 2026

## Confirmed live failure

The original 24 Nov Facebook Daily Rates photo was published and independently verified. At approximately **20:40 SAST**, the read-only identity diagnostic reported:

- HTTP 401
- Meta Graph error `code=190`, `error_subcode=463`
- status `TOKEN_EXPIRED`
- GitHub run: https://github.com/Draztik99/coinoswap/actions/runs/45461948616

This is an expired access token, not a detected Facebook POST failure. The existing publisher checks Page identity before creating a date reservation or any public post. Automatic Facebook Daily Rates will fail closed until credentials are restored. **Instagram through Metricool is independent: do not disable it.**

## The shortest safe recovery

**Only the Page credential itself needs to change.** Do not create or publish a test post to validate credentials.

1. Open the Meta Business settings with the Facebook identity that administers the CoinoSwap Page and its app, `CoinoSwap Social Publisher`. Use a dedicated, authorized long-lived Page token for the CoinoSwap Page ID `108130358772133`. Do not reuse the short-lived Graph API Explorer test token (the default user token often expires in about an hour).
2. **Preferred production architecture:** In Meta Business Settings → Users → System users, use an appropriately authorized system user connected to the CoinoSwap Page and the CoinoSwap Social Publisher app. Assign the actual Page and only necessary permissions/tasks (including Page CREATE_CONTENT for publishing, plus ANALYZE for metrics). Confirm required Meta app scopes, for example `pages_show_list`, `pages_manage_posts`, `pages_read_engagement` and supported insights scopes.
3. Generate a properly authorized system-user credential in the Meta Business interface. Meta's official [Pages API system-user instructions](https://developers.facebook.com/docs/business-management-apis/system-users/guides/api-calls/) explain how the system-user token can fetch the **Page access token** through `GET /me/accounts`. Select the record whose `id` is exactly `108130358772133`. **The existing GitHub secret expects the Page token, not the raw system-user token.**
4. Privately check the new Page token with Meta's Access Token Debugger or a GET `/me?fields=id,name`, ensuring that the token identifies the CoinoSwap Page `108130358772133`. Inspect expiry, app, permissions and whether Meta permits the requested Page tasks. Never put the token in a query URL, browser screenshot, GitHub issues, repository source code or this chat. Prefer secure Meta UI; if using HTTP requests, place the credential in an Authorization header rather than in a URL.
5. Open the CoinoSwap repository: https://github.com/Draztik99/coinoswap/settings/environments → choose `facebook-live` → **Environment secrets** → update **`COINOSWAP_FB_PAGE_ACCESS_TOKEN`**. Replace its value with the newly authorized **Page** token. Do not add credentials to GitHub repository variables, workflow YAML or public GitHub issues. A repository secret with the same name is not necessarily the correct scope; preserve the protected `facebook-live` environment.
6. Run the already-deployed read-only workflow in GitHub:
   https://github.com/Draztik99/coinoswap/actions/workflows/facebook-readonly-health.yml
   Choose **Run workflow → main**. It performs only one GET and prints sanitized numeric Meta error identifiers. The required success status is **`VERIFIED_PAGE_IDENTITY`** for Page `108130358772133`. This does **not** post on Facebook or prove all publishing scopes. It confirms the baseline token identity needed before the next scheduled post.
7. After successful GET, monitor the next randomized Facebook publishing slot and independently verified receipt in `docs/daily-rates/facebook-publications/YYYY-MM-DD.json`. Do not manually invoke the live Facebook poster to test the token; avoid duplicate posts.

## Ongoing safeguards

- The GitHub GET-only Page-token health workflow now checks **10:30 and 11:00 SAST** every day (best-effort GitHub schedules).
- The public Facebook publisher is invoked only from the existing `daily-rates.yml` **schedule** and will never post on push, dry-run or normal manual source-generation paths.
- An invalid token blocks posting and leaves Instagram Metricool untouched. The existing 14:55/14:59 SAST publication monitors report missing Facebook receipts without auto-republishing.
- Meta may invalidate long-lived or system-user credentials for access changes, app changes, policy events and other reasons. Even tokens reported without a fixed expiry need ongoing monitoring and secure rotation.
- The analytics collector retains historical reports when Meta auth fails but explicitly marks its collection run failed.
- No new automation was added in ChatGPT; the user's five scheduled-task slots are currently full.

## Current Cloudflare dashboard status

The secure deployment package has already been merged as [PR #13](https://github.com/Draztik99/coinoswap/pull/13), and its [Cloudflare provisioning guide](../social-analytics/CLOUDFLARE_DEPLOYMENT.md) is ready. **The Cloudflare Pages project and Cloudflare Access policies are not yet created/verified**, because account-owner Cloudflare authorization is required. Do not set `COINOSWAP_TEAM_ACCESS_VERIFIED=true` or expose reports before protecting production and preview hostnames.

## Official Meta documentation (checked 24 November 2026)

- [Graph API error handling: 190, subcode 463](https://developers.facebook.com/docs/graph-api/guides/error-handling)
- [System users and Pages API calls / derive Page tokens](https://developers.facebook.com/docs/business-management-apis/system-users/guides/api-calls/)
- [Install apps and generate system-user credentials](https://developers.facebook.com/docs/business-management-apis/system-users/install-apps-and-generate-tokens/)
- [Debugging and checking access token validity](https://developers.facebook.com/docs/facebook-login/guides/%20access-tokens/debugging/)
