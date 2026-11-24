# CoinoSwap direct publishing — isolated shadow foundation

**Status: DEVELOPMENT ONLY / ZERO SOCIAL PUBLISHING CAPABILITY.**
This directory has **no function capable of sending social posts**. The
Facebook-only health diagnostic supports one **manual GET** to identify the
Page token subject; it has no publishing API, automatic schedule or secret storage.
Everything else in this folder remains offline/shadow only.

## Verified architecture inputs

Existing immutable main-branch assets are located at
`docs/daily-rates/YYYY-MM-DD.png` and `docs/daily-rates/YYYY-MM-DD.json`.
`asset_reader.py` verifies both together using a pinned 40-character Git
commit SHA, current SAST date, PNG dimensions, SHA-256 image digest, verified
BTC/ETH/XMR quotations, two-source deviation, five-minute quote freshness,
and selected posting-window expiry.

The GitHub audit's `approval_state` tracks **image preparation**, not an
authoritative social publication receipt. Metricool remains the live FB/IG
publisher; its existing automations have not been changed.

## Offline test / local preview (no publisher calls)

```shell
python -m unittest discover -s social-publisher/tests -v
python social-publisher/dry_run.py \
  --audit docs/daily-rates/YYYY-MM-DD.json \
  --image docs/daily-rates/YYYY-MM-DD.png
```

Replace the sample date with the current SAST date. If the image/quotes are
too old for publication, the command correctly returns `BLOCKED`. This is
not a failure of the archived image: historical assets are deliberately
non-publishable. For fixture tests only, `--at-sast 2026-11-23T14:49:00+02:00`
can override the time when using local files.

To inspect official assets at a single known revision using GitHub read-only
GET requests (this still does not post):

```shell
python social-publisher/dry_run.py --commit-sha <PINNED_MAIN_COMMIT_SHA>
```

## Facebook Page identity health (explicit, read-only)

The owner confirmed a Page token from Meta Graph API Explorer and that
`GET /me?fields=id,name` identifies Coinoswap Page `108130358772133`.
To repeat this check in an **isolated local environment** using a separately
supplied Page token, use the manual `facebook_health.py --check` command.
It does not execute when imported or during CI, and never posts.

- Supply `COINOSWAP_FB_PAGE_ACCESS_TOKEN` through a trusted secrets mechanism
  in the process environment (not via a CLI argument or code).
- Never put the token in GitHub source, workflow YAML, command history, issues
  or chat. Do not enable Actions secrets for this offline branch.
- The single HTTPS GET is to Meta's fixed `/me?fields=id,name` endpoint,
  using an Authorization header. Redirects are refused, timeouts bounded,
  and outputs contain only fixed classifications and public Page identity.
- `VERIFIED_PAGE_IDENTITY` checks **identity only**; it does not prove
  expiry, renewal, app publishing mode, permission approval or posting rights.
- For offline testing only, run `python -m unittest discover -s social-publisher/tests -v`.

Existing Metricool remains the production publisher. No Facebook POSTs
are implemented or authorized.

## Cross-run durable ledger (prototype, not deployed)

`postgres_schema.sql` provides a PostgreSQL schema with an atomic unique
`(platform,date_sast,campaign_key)` key and restrictive lifecycle states.
`pg_ledger.py` uses an injected DB-API-compatible connection factory for
atomic `INSERT ... ON CONFLICT DO NOTHING` reservations, compare-and-swap state
transitions and independently verified Metricool receipt adoption. Offline
mock tests cover collisions, UNKNOWN outcomes and receipt requirements.

**No managed PostgreSQL instance, credentials, migrations, cross-process
integration test or production publisher has been configured.** The SQL is a
deployment proposal; do not point these tests at a live database.

## Facebook read-only published-post reconciliation

`facebook_reconciliation.py` and the explicitly invoked
`facebook_page_readback.py --check` can flag likely existing Daily Rates
posts using Page published-post GET responses. This is a *warning*, never
proof of no duplicates: missing messages, partial pagination or Metricool
automations require independent reconciliation. The script exits non-zero
for all outcomes to prevent interpreting it as permission to publish.

## Local ledger prototype

`ledger.py` uses a UNIQUE composite key
`(platform, date_sast, campaign_key)` and compare-and-swap transitions.
Unknown delivery outcomes are never blindly resent. It is an **offline
single-host SQLite prototype**, not a cross-run distributed ledger. Before
any actual scheduling, migrate to a single **durable managed database**
shared across all workers and ensure that any possible prior Metricool
publication is reconciled for that platform and day.

## Explicit non-goals of this milestone

- No X, Instagram, or Facebook publishing, media upload, or OAuth. The manual Facebook identity check is GET-only.
- No GitHub Actions production schedule or live credentials.
- No new posts on any public social account.
- No edits to `main`, Daily Rates scripts, or Metricool automations.
- No assertion that website visits or completed swaps can yet be attributed.

## Next implementation gate

Integrate provider contract mocks, build approved image-format derivatives,
and agree on a managed publication ledger, permissions and account-specific
API pricing. Only after all shadow-mode tests and separate approval should
live providers be implemented. Keep Facebook/Instagram direct-live disabled
while Metricool publishes the same campaigns.

Full roadmap: `docs/direct-social/INTEGRATION_PLAN.md`.
