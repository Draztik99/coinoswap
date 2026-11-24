# CoinoSwap — Manual fresh Daily Rates first photo post

**Scope:** Facebook Page 108130358772133 only. **No schedule.**  
**Prerequisites:** the Page token must already exist as the GitHub `facebook-live` environment secret `COINOSWAP_FB_PAGE_ACCESS_TOKEN`, and CoinMarketCap key as `CMC_API_KEY` accessible to the generator. Facebook delivery for the Daily Rates campaign must be disabled on Metricool; do not touch Metricool Instagram.

## When to use

For a **manually approved first live BTC/ETH/XMR Daily Rates image post**, when the current-day image has not been produced and the normal daily slot has passed. This recovery creates a fresh, dated image from the established CMC+Kraken checks and attempts exactly one direct Facebook photo POST.

## Single-run sequence

1. Open GitHub Actions → `CoinoSwap Facebook — Fresh Daily Rates Rescue (MANUAL LIVE POST)`.
2. Select **main** and use **Run workflow**.
3. Type the exact release phrase: `I_APPROVE_FRESH_COINOSWAP_DAILY_RATES_POST`.
4. Check **Metricool Facebook disabled** only when Facebook Daily Rates delivery truly is disabled. Keep Instagram on Metricool.
5. The workflow validates that today's `docs/daily-rates/YYYY-MM-DD.{json,png}` pair does **not** already exist, installs the official render dependencies, retrieves fresh CMC and Kraken quotes, renders the official CoinoSwap template, and validates the PNG/date/checksum/quote timing.
6. It commits today's asset pair to `main` in the same job and pins the resulting immutable commit SHA, waits for the audit's publication target, then independently re-fetches and validates that exact commit.
7. It checks Meta Page identity and the Page's published-post history; creates the immutable `coinoswap-facebook-daily-rates-YYYY-MM-DD` Git reservation tag, attempts exactly one photo POST, and independently reads the result.
8. GitHub displays `PUBLISHED` with the Facebook public URL after independent verification, `BLOCKED` if safety conditions do not pass, or `UNKNOWN` after an uncertain POST. **Never rerun on UNKNOWN, and never delete/force-update the reservation tag.** Verify the actual Page manually.

## Guardrails and limitations

- **No automatic trigger**: only a human-initiated `workflow_dispatch` with explicit typed approval.
- The existing Daily Rates generator schedule and Metricool automations are not changed.
- If the current-day pair exists, abort; do not post stale/duplicate assets.
- Quotes must pass existing CoinMarketCap/Kraken time and deviation checks; image generation must finish before the freshness cutoff.
- Meta can be called only by the pre-existing protected manual sender; no token appears in source code or console output.
- GitHub Actions may take too long for the image to be usable at the chosen emergency target. In that case, **fail closed** instead of relaxing freshness checks or resubmitting a potentially published post.
- The Meta POST cannot be dispatched by this ChatGPT GitHub connector. It requires the authorized GitHub repository user to click **Run workflow**.
- This verifies manual image publishing only, not future unattended daily-rate delivery. Automatic direct Facebook scheduling requires a separate cutover design and approval.
- If the CoinMarketCap secret is missing or an API quote fails, no image or Facebook post is created.
- If the GitHub push succeeds but Facebook posting fails or is blocked, today's source files remain. Do not use retries or manually edit reservations without investigating.
