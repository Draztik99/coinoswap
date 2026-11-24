# CoinoSwap Facebook-only publishing — release blockers and 24 Nov incident

**Captured:** Tuesday 24 November 2026, after 17:34 SAST.  
**Scope:** Facebook Page `108130358772133`. Instagram direct API remains on hold.  
**Production policy:** No changes to `main`, GitHub Daily Rates scheduler, Metricool, or existing ChatGPT automations. This report does **not** authorize publishing.

## Incident: today's Daily Rates asset was not produced

**Direct GitHub repository inspection:**
- Current `main` Daily Rates directory has `2026-11-22.{json,png}` and `2026-11-23.{json,png}`.
- Both `docs/daily-rates/2026-11-24.json` and `2026-11-24.png` return HTTP 404.
- The source job `.github/workflows/daily-rates.yml` generates only and must pass `daily-rates/should_prepare.py` before calling `prepare_rates.py`.
- `daily-rates/posting_slots.py` selected Tuesday 24 Nov 2026 **14:30 SAST**; expected generation **14:26–14:28 SAST**. No rate or image should be reused after that time.

**Actual GitHub Actions audit:**
- [Schedule run 45271339557](https://github.com/Draztik99/coinoswap/actions/runs/45271339557) started **23 Nov 21:36 UTC / 23:36 SAST**. It logged `selected=False` and skipped all generator/image commit steps.
- [Schedule run 45294204878](https://github.com/Draztik99/coinoswap/actions/runs/45294204878) started **24 Nov 00:05 UTC / 02:05 SAST**. It logged `selected=False` and skipped generator/image commit steps. GitHub marked the workflow success because checking the slot was successful.
- No corresponding scheduled GitHub run at the required **12:26 UTC / 14:26 SAST** appears in the available 24 Nov `main` Actions history. The underlying reason for absent or mistimed dispatches is not confirmed; do not misstate this as an image-rendering or price API failure.

**Independent existing automation observations (read-only):**
- CoinoSwap Rates half-hour watcher: 24 Nov 14:29 SAST skipped 14:30 slot safely (required manifest missing).
- CoinoSwap Rates hourly+audit watcher: 24 Nov 14:59 SAST could not verify Facebook/Instagram publication; today's manifest missing.
- Both automations remain enabled. An enabled watcher is *not* evidence a rate was published.

## Why a green CI badge cannot authorize direct publishing

- Facebook Page-token `GET /me?fields=id,name` and `CREATE_CONTENT` were confirmed by the owner in Meta Graph API Explorer, **but** expiry, app mode and token storage are not production-validated.
- Development-only Facebook shadow, receipt parsing, Page ownership verification, PostgreSQL schema, idempotency, and redacted health/readback tools are **not** live publication transport.
- Feature-branch CI runs a disposable PostgreSQL service and mocked Graph API tests, **not** a production Meta POST.
- Current official asset URL cannot point to a validated image dated 24 Nov 2026, so even an otherwise ready publisher would have to skip today.
- The existing Metricool Facebook+Instagram automations must not overlap with a direct Facebook publisher.

## Non-negotiable release gates

1. **Reliable generation** — tomorrow's and subsequent daily assets must be generated before each chosen slot. Using GitHub scheduled Actions with a 2–3 minute acceptance window has no dispatch-time guarantee. Prefer a reliable scheduler/server with a tightly monitored execution window and fail-closed skip if late; validate with multiple days of actual successful delivery.
2. **Secret lifecycle** — provision the Page token via a reviewed restricted secrets mechanism, verify Meta app/Page authorization and expiration/invalidation status. Never put tokens in chat, Git commits or screenshots.
3. **Durable ledger deployment** — provision real shared PostgreSQL, run migration, verify atomic reservations with multiple workers, document backups/retention and restore.
4. **Authoritative anti-duplication** — reconcile existing Metricool activity, Graph Page posts and prior automation receipts. If any source is ambiguous: BLOCK, do not retry automatically.
5. **Real transport** — implement separately reviewed POST `/{page-id}/photos` with explicit approval, immediately read back `id,from{id},page_story_id,link`, and permit `PUBLISHED` ledger state only with matching CoinoSwap Page evidence.
6. **Observability/rollback** — operational alerts on source missing, late generator, 401/403/429, token invalidation, unknown delivery. Rehearse rollback to Metricool with no duplicate sends.
7. **Authorized cutover** — explicit Facebook-only production permission after shadow sign-off, disable overlapping Metricool *Facebook* campaign delivery first, retain Metricool *Instagram* separately.

## Suggested diagnosis/remediation for the GitHub generator

Inspect GitHub Actions' schedule activity/settings and UTC run dispatch for the target slots; check whether schedule updates on the default branch have fully taken effect, are delayed or missing, and whether any repository-level action restrictions exist. Review event payloads (including `github.event.schedule`) and chronology of workflow edits; do not assume a precise GitHub internal cause from `selected=False`. Schedule a dedicated independent job/watchdog to mark 'missing generation' **failed**, since today's run was misleadingly green. Do **not** simply extend the five-minute quote freshness limit to mask late execution.

If a reliable timer cannot be guaranteed via hosted GitHub Actions, execute generation on a more predictable always-on worker and keep the existing verified `docs/daily-rates/YYYY-MM-DD.{json,png}` artifact contract for downstream automation.

## Outcome

**NO-GO FOR PUBLICATION as of 24 November 2026.** Continue development and testing on the isolated feature branch; no changes to live publishing services, no accidental late posts and no use of yesterday's image.
