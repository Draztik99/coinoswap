"""Git-based, append-only publication reservations; no external database.

A successful reservation push MUST happen before a Facebook POST. Re-running,
network uncertainty, or an already-existing remote tag blocks a second send.
Never delete or force-update reservation tags. Intended for a single GitHub
repository with protected environment and serialized publish workflow.
"""
from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

TAG_PREFIX = "coinoswap-facebook-daily-rates-"


class ReservationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class TagReservation:
    repository: Path

    def reserve(self, date_sast: str, *, request_id: str | None = None) -> str:
        from datetime import date
        try:
            if date.fromisoformat(date_sast).isoformat() != date_sast:
                raise ValueError()
        except (TypeError, ValueError) as exc:
            raise ReservationBlocked("invalid reservation date") from exc
        tag = TAG_PREFIX + date_sast
        request_id = request_id or uuid.uuid4().hex
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", request_id):
            raise ReservationBlocked("invalid reservation nonce")
        repo = Path(self.repository)
        # No secrets in arguments. Never dump Git stderr, which may contain
        # remote or credential details. Do not automatically retry any push.
        try:
            exists = subprocess.run(
                ["git", "ls-remote", "--exit-code", "--refs", "origin", "refs/tags/" + tag],
                cwd=repo, capture_output=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReservationBlocked("reservation lookup failed") from None
        if exists.returncode == 0:
            raise ReservationBlocked("this date is already reserved")
        if exists.returncode != 2:
            raise ReservationBlocked("reservation lookup unavailable")
        tag_command = [
            "git", "-c", "user.name=CoinoSwap FB Publisher",
            "-c", "user.email=coinoswap-fb@users.noreply.github.com",
            "tag", "-a", tag, "-m", "FB daily rates reservation: " + request_id,
        ]
        try:
            created = subprocess.run(tag_command, cwd=repo, capture_output=True,
                                     timeout=15, check=False)
            if created.returncode != 0:
                raise ReservationBlocked("local reservation failed")
            pushed = subprocess.run(
                ["git", "push", "origin", "refs/tags/" + tag],
                cwd=repo, capture_output=True, timeout=20, check=False,
            )
            if pushed.returncode != 0:
                raise ReservationBlocked("reservation push failed; no post attempted")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReservationBlocked("reservation operation failed; no post attempted") from None
        return tag
