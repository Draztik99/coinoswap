// CoinoSwap Daily Rates: independent Cloudflare Cron -> GitHub Actions BACKUP.
// No Meta or Metricool endpoint exists here. Never logs GitHub credentials.
// Deployment is INACTIVE until the Worker and its secret are configured.
export const GITHUB_WORKFLOW_DISPATCH =
  "https://api.github.com/repos/Draztik99/coinoswap/actions/workflows/daily-rates.yml/dispatches";

// Each UTC trigger is 9 or 4 minutes ahead of a SAST 11:30–14:30 slot.
// The GitHub prepare gate independently checks the selected randomized day,
// original fresh-quote window, and immutable previous source.
const UTC_TRIGGER_HOURS = new Set([9, 10, 11, 12]);
const UTC_TRIGGER_MINUTES = new Set([21, 26, 51, 56]);

export function isExpectedTrigger(scheduledTime) {
  if (!Number.isFinite(scheduledTime)) return false;
  const d = new Date(scheduledTime);
  if (Number.isNaN(d.getTime())) return false;
  const hour = d.getUTCHours();
  const minute = d.getUTCMinutes();
  return UTC_TRIGGER_HOURS.has(hour)
    && UTC_TRIGGER_MINUTES.has(minute)
    && (hour !== 12 || (minute === 21 || minute === 26));
}

export async function runScheduledBackup(event, env, fetchFn = fetch) {
  if (!event || !isExpectedTrigger(event.scheduledTime)) {
    return { status: "SKIPPED_UNEXPECTED_TIME" };
  }
  const token = env?.GITHUB_ACTIONS_TOKEN;
  if (typeof token !== "string" || !token || token !== token.trim()
      || /[\s\x00-\x1f\x7f]/.test(token)) {
    throw new Error("Cloudflare backup dispatch secret is not configured");
  }

  const payload = JSON.stringify({
    ref: "main",
    inputs: { emergency: "false", backup_trigger: "true" },
  });
  // This credential needs fine-grained Actions:write on ONLY Draztik99/coinoswap.
  // It is never sent to Meta, GitHub logs, the dashboard or browser clients.
  let response;
  try {
    response = await fetchFn(GITHUB_WORKFLOW_DISPATCH, {
      method: "POST",
      headers: {
        Authorization: "Bearer " + token,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "CoinoSwap-Rates-Backup-Cron/1.0",
      },
      body: payload,
    });
  } catch {
    throw new Error("Cloudflare backup dispatch request unavailable");
  }
  // GitHub Actions workflow_dispatch returns HTTP 204 when accepted,
  // NOT proof that a Facebook post has been sent.
  if (response.status !== 204) {
    throw new Error("GitHub backup dispatch rejected (HTTP " + response.status + ")");
  }
  return { status: "DISPATCH_ACCEPTED_NOT_PUBLISHED" };
}

export default {
  async scheduled(event, env) {
    return runScheduledBackup(event, env);
  },
  async fetch() {
    return new Response("Not found", { status: 404 });
  },
};
