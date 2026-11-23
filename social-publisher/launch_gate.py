"""Immutable launch guard and cross-publisher coordination preflight.

A positive readiness assessment does not send posts or grant permission.
No social publish adapter or credential access exists in this codebase.
"""
from __future__ import annotations

from dataclasses import dataclass

PLATFORMS = {"x", "facebook", "instagram"}


@dataclass(frozen=True)
class GateResult:
    ready_for_further_live_integration: bool
    reason: str


def evaluate_release_gate(
    platform: str,
    *,
    explicitly_approved: bool = False,
    production_credentials_verified: bool = False,
    authoritative_shared_ledger: bool = False,
    metricool_active: bool = True,
    external_publication_checked: bool = False,
    verified_shadows: bool = False,
) -> GateResult:
    """Fail closed on absent approval, credentials or cross-publisher conflict."""
    if platform not in PLATFORMS:
        return GateResult(False, "unsupported platform")
    if not explicitly_approved:
        return GateResult(False, "no explicit live API posting approval")
    if metricool_active:
        return GateResult(False, "Metricool remains an active publisher for this platform")
    if not external_publication_checked:
        return GateResult(False, "external-post duplicate reconciliation not completed")
    if not production_credentials_verified:
        return GateResult(False, "production API permissions/credentials not verified")
    if not authoritative_shared_ledger:
        return GateResult(False, "durable shared idempotency ledger not ready")
    if not verified_shadows:
        return GateResult(False, "shadow-mode testing not signed off")
    return GateResult(True, "preconditions met; separate live deployment still required")
