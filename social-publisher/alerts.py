"""Offline alert payload generation; zero email/chat/webhook sends."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Alert:
    severity: str
    platform: str
    date_sast: str
    state: str
    description: str


def redact_failure_detail(raw: str) -> str:
    """Mask tokens even when an upstream error mistakenly includes secrets."""
    detail = str(raw)
    detail = re.sub(r"(?i)Bearer\s+[^\s]+", "Bearer [REDACTED]", detail)
    detail = re.sub(
        r"(?i)\b(access_token|refresh_token|api_key|client_secret|password)\b"
        r"\s*[:=]\s*[^&\s,;]+",
        lambda m: m.group(1) + "=[REDACTED]",
        detail,
    )
    return detail[:500]


def publication_alert(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    state = row.get("state")
    if state not in {"UNKNOWN", "FAILED_PRE_SEND"}:
        return None
    alert = Alert(
        severity="CRITICAL" if state == "UNKNOWN" else "WARNING",
        platform=str(row.get("platform", "unknown"))[:30],
        date_sast=str(row.get("date_sast", "unknown"))[:30],
        state=state,
        description=redact_failure_detail(row.get("last_error") or state),
    )
    # A structured unsent payload to a future approved alert dispatcher.
    return asdict(alert)
