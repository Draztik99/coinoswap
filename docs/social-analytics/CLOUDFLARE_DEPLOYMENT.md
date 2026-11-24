# CoinoSwap Analytics — Cloudflare Pages + Cloudflare Access release checklist

**Date:** 24 November 2026 (SAST)  
**Scope:** Host **one private, read-only team dashboard**, no Windows PC, no VPS, no modifications to coinoswap.com or live publishing.  
**Status:** GitHub deployment artifact prepared; Cloudflare account setup and Access verification are **not yet completed**. Do not claim a live Cloudflare dashboard.

## Architecture

\`\`\`
CoinoSwap publisher + Metricool -> validated GitHub receipts / public aggregate metrics
-> existing GitHub Analytics Collector (scheduled 19:05 SAST)
-> Git commit: docs/social-analytics/snapshots + dashboard
-> Cloudflare Pages GitHub integration on main
-> SECURITY GATE: initially publish placeholder, NOT dashboard
-> Cloudflare Access: allow only approved team email identities
-> after confirming Access protection on every hostname: activate HTML + CSV export
\`\`\`

Cloudflare Pages handles HTTPS, global hosting and auto deployment. No local PC, VM, server patching, backend or Cloudflare API token required for static reporting. Dashboard is read-only. GitHub is still the analytics source and content publisher. Team members never need GitHub or a local Python install.

**Important security boundary:** Our GitHub repository \`Draztik99/coinoswap\` is PUBLIC. Social aggregate records stored there are already public independently of Cloudflare Access. No future website session identifiers, private user events, nonpublic revenue, swap IDs, customer records, API keys or confidential attribution data may ever be committed to this repository. When those capabilities are connected, move them to private managed storage and deliver to authenticated users only.

## Step 1 — Create an isolated Pages project (requires operator's Cloudflare login)

Visit https://dash.cloudflare.com/ → Workers & Pages → Create → Pages → **Connect to Git** → GitHub.

Select only the GitHub repository **Draztik99/coinoswap**, not all repositories, when granting the Cloudflare GitHub App access.

Choose a free/available project slug, for example \`coinoswap-analytics-team\`. The actual available project slug is decided by Cloudflare; do not claim that the hostname exists until Cloudflare assigns it.

Set the following build configuration (no npm packages, no application server):

| Field | Value |
| --- | --- |
| Framework preset | None |
| Production branch | \`main\` |
| Root directory | \`/\` (repository root) |
| Build command | \`python3 social-publisher/insights/cloudflare_build.py\` |
| Build output directory | \`dist\` |
| Build environment: PYTHON_VERSION | 3.12.10 (pin to tested Python 3.12 branch) |
| Build environment: SKIP_DEPENDENCY_INSTALL | 1 (stdlib-only; avoid unnecessary package installation) |
| Initially configure \`COINOSWAP_TEAM_ACCESS_VERIFIED\`? | **No. Leave absent / false.** |
| Preview branch deployments | **None / disabled** until preview Access is configured |
| GitHub App authorization | **Only Draztik99/coinoswap** |

The initial build intentionally produces \`LOCKED_PLACEHOLDER\`: an uninformative setup page with **zero analytics files**. It is safe for that placeholder to be briefly reachable during Access setup, but **do not turn on actual dashboard data** before Step 3 is complete. Cloudflare Git-integrated projects automatically rebuild on \`main\` changes.

## Step 2 — Cloudflare Access policy (protect production AND previews)

**Critical:** Pages Settings → General → **Enable access policy** alone protects *preview* URLs, **not** the primary production \`<project>.pages.dev\` hostname. See Cloudflare's known-issues guide:
https://developers.cloudflare.com/pages/platform/known-issues/#enable-access-on-your-pagesdev-domain

After the project exists:
1. Under the Pages project's Settings, **Enable access policy** and select **Manage** for the created policy.
2. In Zero Trust → Access controls → Applications, open the Pages application and select **Configure**.
3. In **Public hostname**, remove the leading wildcard \`*\` from the Subdomain field and save; this secures the production \`<project>.pages.dev\` hostname. Rename the Access application if necessary.
4. Go back to Pages Settings and **Enable access policy again** to make a separate Access application for preview deployment hostnames (\`*.<project>.pages.dev\`), even if branch previews are disabled for now.
5. Verify the resulting production and preview Access applications both exist and have sensible allow rules.
6. Add only **specific approved team email addresses** to an \`Allow\` policy; do **not** allow \`Everyone\`, all email addresses, public domain-wide access or bypass rules.
7. Use your organization's identity provider/SSO or the **One-time PIN** identity provider. One-time PIN may need to be added explicitly in current Cloudflare Zero Trust accounts: https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/
8. Choose an appropriate Access session expiry, for example one day; review team member removals periodically.

**Before releasing data:** Open the production Pages URL in a private/incognito window. It must demand Cloudflare Access authentication or deny access. Repeat with an unapproved email and, if enabled, a preview URL. Sign in once with an approved team identity and confirm the placeholder page is visible. Never treat \`robots.txt\`, noindex or HTTP headers as authentication; only Cloudflare Access is the login control.

## Step 3 — Explicitly release team dashboard after verifying Access

Only **after** Step 2 succeeds, go to Pages project → Settings → Environment variables (Production) and set:

\`\`\`
COINOSWAP_TEAM_ACCESS_VERIFIED=true
\`\`\`

Then redeploy the production \`main\` branch (or allow the next GitHub commit to trigger an automatic deployment).

The \`CF_PAGES_BRANCH=main\` system variable is injected by Cloudflare Pages automatically. If either condition is absent, the build remains locked. **This flag is not a substitute for Cloudflare Access**: it is only a manual safety interlock preventing an accidental analytics deployment before Access is configured.

Once released, the \`dist\` artifact includes exactly:

- \`index.html\`: black-and-gold verified metrics dashboard.
- \`reports/post-performance.csv\`: CSV download of verified brand-owned aggregate post metrics only.
- \`_headers\`: CSP, noindex, no-referrer, no-store; defense in depth, not auth.
- \`robots.txt\`: disallow crawling; defense in depth, not auth.

**No** raw GitHub snapshots, input JSON, backend files, source code, secrets or website visitor data is copied to the Pages deployable folder. All PDF and secure export/report features for sensitive data are later development milestones.

## Step 4 — Verify availability, data updates and access revocation

1. From an **unapproved/unauthed** browser, dashboard must **not** display either HTML metrics or the \`/reports/post-performance.csv\` file; authentication/deny expected for BOTH.
2. From an **approved** team login, dashboard must show real Facebook/Instagram post rows. The CSV must download and have \`N/A\` for missing metrics, never guessed zeros.
3. Change a test analytics snapshot on \`main\` only through the verified GET-only collector and confirm GitHub Pages build triggers automatically. **Never submit new social posts just to test dashboards.**
4. Confirm the Pages deployment/Access audit shows successful authorization, and inspect headers for noindex/no-store.
5. Test team access removal by revoking one test user's allow policy and expiring their Access session; review that access is denied.
6. Keep preview deployments off, or protect wildcard preview URLs through the separate Access app. Old preview hashes can remain accessible while a deployment is retained.
7. The optional custom hostname \`analytics.coinoswap.com\` can be added later with its own Access application. **Do not touch coinoswap.com DNS now**. Cloudflare documents a known issue when an Access policy is configured on a custom hostname before it is attached to Pages—attach/verify the domain first, then protect it.
8. If data freshness degrades, the existing collector/workflow remains independent of Pages. A build error must **not** stop Facebook or Instagram posts.

## Emergency disable / rollback

- To remove the current report from new deployments, set \`COINOSWAP_TEAM_ACCESS_VERIFIED=false\` (or remove it), and redeploy. This creates only the placeholder.
- **Do not remove Cloudflare Access** or publicly expose retained prior deployment URLs; keep the Access policies in force, including previews.
- If the project is compromised, pause Pages production deployments and revoke/rotate authorized sessions/policies as needed. This does not change social post workflows.
- A Cloudflare outage should never stop GitHub scheduled metric collection or other publishing automations.

## Known limitation to clear

No Cloudflare integration is connected through the current ChatGPT tooling, so an assistant cannot access your Cloudflare account or silently authorize the GitHub OAuth connection, create the Pages project, define team Access identities or verify the live URL. Those account-owner authorization steps require a Cloudflare login. The repository build/test preparation is safe to complete before then.

## Vendor documentation

- GitHub ↔ Pages: https://developers.cloudflare.com/pages/configuration/git-integration/
- Pages build config: https://developers.cloudflare.com/pages/configuration/build-configuration/
- Preview restrictions: https://developers.cloudflare.com/pages/configuration/preview-deployments/
- **Protect both production and preview:** https://developers.cloudflare.com/pages/platform/known-issues/#enable-access-on-your-pagesdev-domain
- Zero Trust policies: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
- One-time PIN: https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/
