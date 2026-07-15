from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.config import settings


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds)
