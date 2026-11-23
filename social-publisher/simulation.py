"""Completely offline mock social delivery state machine.

No API clients, HTTP transport, credentials, or outgoing network calls.
Only simulates provider outcomes and tests ledger safety.
"""
from __future__ import annotations

from dataclasses import dataclass

from ledger import PublicationLedger

ALLOWED_OUTCOMES = {
    "success", "timeout_after_send", "http_401", "http_429", "http_500",
    "receipt_missing", "pre_send_failure",
}


@dataclass(frozen=True)
class MockOutcome:
    kind: str
    provider_id: str = ""
    public_url: str = ""


@dataclass(frozen=True)
class SimulationResult:
    state: str
    reserved: bool
    post_count: int


def simulate_publication(
    ledger: PublicationLedger,
    platform: str,
    date_sast: str,
    image_sha256: str,
    outcome: MockOutcome,
    campaign_key: str = "daily_rates",
) -> SimulationResult:
    """Run fake endpoint response through the real reservation state machine."""
    if outcome.kind not in ALLOWED_OUTCOMES:
        raise ValueError("unknown simulated delivery outcome")
    if not ledger.reserve(platform, date_sast, campaign_key, image_sha256, f"mock:{outcome.kind}"):
        row = ledger.get(platform, date_sast, campaign_key)
        return SimulationResult(row["state"], False, 0)
    if outcome.kind == "pre_send_failure":
        ledger.transition(
            platform, date_sast, campaign_key,
            from_state="RESERVED", to_state="FAILED_PRE_SEND",
            error="simulated validation/credential failure before send",
        )
        return SimulationResult("FAILED_PRE_SEND", True, 0)

    ledger.transition(platform, date_sast, campaign_key,
                      from_state="RESERVED", to_state="SENDING")
    if outcome.kind == "success" and outcome.provider_id and outcome.public_url:
        ledger.transition(
            platform, date_sast, campaign_key,
            from_state="SENDING", to_state="PUBLISHED",
            provider_post_id=outcome.provider_id,
            public_url=outcome.public_url,
        )
        # Simulated provider receipt only; not a real-world post.
        return SimulationResult("PUBLISHED", True, 1)

    # Always fail safe after an attempted send. Even explicit errors require
    # reconciliation instead of an unsafe blind retry.
    ledger.transition(
        platform, date_sast, campaign_key,
        from_state="SENDING", to_state="UNKNOWN",
        error=f"simulated provider outcome {outcome.kind}",
    )
    return SimulationResult("UNKNOWN", True, 0)
