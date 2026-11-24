# CoinoSwap — approved recurring Facebook Daily Rates launch

**Approved by operator:** 24 November 2026 (SAST), recurring PUBLIC direct Facebook Daily Rates posts, one each day between **11:30 and 14:30 SAST**.  
**Platform boundaries:** Facebook via CoinoSwap Graph API on GitHub Actions; Instagram via existing Metricool ChatGPT automation watchers. Facebook delivery through Metricool remains disabled.  
**Page:** 108130358772133.  
**Status:** Prepared for production release after CI + merge; do not consider an actual next-day post verified until the next eligible scheduled run succeeds.

## Scheduling

The existing `daily-rates/posting_slots.py` selects from seven fixed times:
11:30, 12:00, 12:30, 13:00, 13:30, 14:00, 14:30 SAST.

Weekly seeded shuffle uses every slot **once per Monday–Sunday week** and varies which weekday receives it. This is randomized with balanced coverage rather than arbitrary unbalanced times. There is one candidate each day.

GitHub generator `.github/workflows/daily-rates.yml` creates a source image only on the selected day-slot, with redundant attempts at -4, -3 and -2 minutes. Only a newly generated asset commit enables `publish-facebook`, and **only** for the GitHub `schedule` event on `main`. Manual emergency image generation never auto-publishes to Facebook.

The publisher reads the immutable generator commit, waits for the manifest target, checks five-minute quote freshness from CoinMarketCap + Kraken, exact image hash/date, correct Page identity and publication history. It pushes an immutable per-day reservation tag *before* one Meta photo POST, verifies the post, then records its public URL and post ID in `docs/daily-rates/facebook-publications/YYYY-MM-DD.json`. Uncertain/late events do not retry the Meta POST automatically.

## Live monitoring

- `facebook-readonly-health.yml`: scheduled 11:00 SAST GET-only Page-token identity probe (not a proof of expiry lifetime).
- `daily-rates-readiness.yml`: scheduled 14:41 SAST source image alarm.
- `facebook-daily-publication-audit.yml`: scheduled 14:55 SAST receipt/source integrity alarm.
- Existing ChatGPT 14:59 SAST audit: independent source/Instagram Metricool and direct Facebook evidence review.
- All GitHub schedules are best effort and can be delayed or skipped. Report missing sources/posts, never publish stale data to catch up. Green generator checks that skip are not publication success.

## Emergency pause without disabling Instagram

To stop ONLY scheduled direct Facebook publication, in GitHub repository **Settings → Secrets and variables → Actions → Variables**, set repository variable `COINOSWAP_FB_DAILY_PAUSED` to **`true`**. Source generation and Instagram Metricool workflows remain operational.

The variable is optional and absent by default, so recurring Facebook publication is authorized. Do NOT stop `daily-rates.yml` as a whole just to pause Facebook; that would also suppress the source images required by Instagram.

To resume, remove the pause variable or set it to `false`. Do not change any GitHub secrets or share token values in a chat. The Page token stays in the protected `facebook-live` environment. The publisher still cannot POST on push, tests or manual generation.

## Failed publication and no-blind-retry policy

- Missing source: GitHub generation/monitor alarm, and Instagram watcher skips.
- Meta GET/auth/expiry/rate-limiting failure: Facebook publishing blocked; token health check or GitHub log reports the failure.
- Meta POST timeout/unknown response: Date reservation tag persists; **never force-delete the tag or automatically rerun**. Reconcile Facebook first.
- Independently verified post but failed receipt push: Page may be live. Receipt-only Git pushes can retry safely; never rerun Facebook POST.
- Successful post: receipt includes Page ID, image SHA, immutable source commit, public permalink, GitHub run ID, SAST timestamp and date.

## First launch evidence

The one-time manual Facebook text test and 24 November 2026 BTC/ETH/XMR image post were published and independently read back on the correct Facebook Page. The automated generator and sender have additional **mock-only CI**, which is not the same as an observed unattended publication.

**Do not claim the recurring system has successfully posted until its first actual eligible scheduled run (25 Nov 2026 or next valid day) is verified by Meta receipt.**
