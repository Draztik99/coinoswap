"""Local durable publication-state prototype (SQLite); zero social API calls.

NOT approved as a shared multi-runner production ledger. Future deployment must
use one durable authoritative database reachable by all publication workers.
Unknown outcomes are never automatically re-sent.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

PLATFORMS = {"x", "facebook", "instagram"}
STATES = {"RESERVED", "SENDING", "UNKNOWN", "PUBLISHED", "FAILED_PRE_SEND"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    platform TEXT NOT NULL,
    date_sast TEXT NOT NULL,
    campaign_key TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    request_id TEXT NOT NULL,
    state TEXT NOT NULL,
    provider_post_id TEXT,
    public_url TEXT,
    last_error TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (platform, date_sast, campaign_key)
);
"""


class LedgerError(ValueError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _key(platform: str, date_sast: str, campaign_key: str) -> tuple[str, str, str]:
    if platform not in PLATFORMS:
        raise LedgerError("unknown platform")
    try:
        if date.fromisoformat(date_sast).isoformat() != date_sast:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise LedgerError("invalid SAST date") from exc
    if re.fullmatch(r"[a-z0-9_\-]{2,60}", campaign_key) is None:
        raise LedgerError("invalid campaign key")
    return platform, date_sast, campaign_key


class PublicationLedger:
    """Fail-safe single-host persistence for simulations, not CI run-to-run storage."""

    def __init__(self, filename: str | Path):
        self.filename = str(filename)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.filename, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def reserve(
        self, platform: str, date_sast: str, campaign_key: str,
        image_sha256: str, request_id: str,
    ) -> bool:
        """Reserve exactly one campaign+platform+SAST-day, even after a failure."""
        key = _key(platform, date_sast, campaign_key)
        if re.fullmatch(r"[0-9a-f]{64}", image_sha256) is None:
            raise LedgerError("invalid image hash")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise LedgerError("invalid request id")
        stamp = _utcnow()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """INSERT OR IGNORE INTO posts
                (platform,date_sast,campaign_key,image_sha256,request_id,state,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?)""",
                (*key, image_sha256, request_id, "RESERVED", stamp, stamp),
            )
            conn.commit()
            return cur.rowcount == 1

    def get(self, platform: str, date_sast: str, campaign_key: str) -> dict | None:
        key = _key(platform, date_sast, campaign_key)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM posts WHERE platform=? AND date_sast=? AND campaign_key=?", key
            ).fetchone()
        return dict(row) if row is not None else None

    def transition(
        self, platform: str, date_sast: str, campaign_key: str,
        *, from_state: str, to_state: str, provider_post_id: str | None = None,
        public_url: str | None = None, error: str | None = None,
    ) -> None:
        """CAS transition: never retry/re-send UNKNOWN without reconciliation."""
        key = _key(platform, date_sast, campaign_key)
        allowed = {
            ("RESERVED", "SENDING"),
            ("RESERVED", "FAILED_PRE_SEND"),
            ("SENDING", "UNKNOWN"),
            ("SENDING", "PUBLISHED"),
            ("UNKNOWN", "PUBLISHED"),  # after external receipt reconciliation
        }
        if (from_state, to_state) not in allowed:
            raise LedgerError("invalid state transition")
        if to_state == "PUBLISHED" and (not provider_post_id or not public_url):
            raise LedgerError("published receipt requires provider id and URL")
        if error and len(error) > 1000:
            error = error[:1000]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """UPDATE posts SET state=?,provider_post_id=?,public_url=?,
                last_error=?,updated_at_utc=?
                WHERE platform=? AND date_sast=? AND campaign_key=? AND state=?""",
                (to_state, provider_post_id, public_url, error, _utcnow(), *key, from_state),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise LedgerError("missing record or unexpected current state")
            conn.commit()
