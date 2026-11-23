# CoinoSwap direct publishing — isolated shadow foundation

**Status: DEVELOPMENT ONLY / ZERO SOCIAL PUBLISHING CAPABILITY.**
This directory contains no X or Meta API implementation, no token access,
and no function that can send a social post.

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

## Local ledger prototype

`ledger.py` uses a UNIQUE composite key
`(platform, date_sast, campaign_key)` and compare-and-swap transitions.
Unknown delivery outcomes are never blindly resent. It is an **offline
single-host SQLite prototype**, not a cross-run distributed ledger. Before
any actual scheduling, migrate to a single **durable managed database**
shared across all workers and ensure that any possible prior Metricool
publication is reconciled for that platform and day.

## Explicit non-goals of this milestone

- No X, Instagram, or Facebook publishing, media upload, or OAuth.
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
