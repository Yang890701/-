from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import MetadataChangeLog

SENSITIVE_ROLE_FIELDS = {"read_roles", "export_roles"}
SENSITIVE_COLUMNS = {"contact_phone", "rent", "rent_amount", "electricity_amount", "total_amount"}


def requires_second_approval(before: dict[str, Any] | None, after: dict[str, Any] | None) -> bool:
    if not before or not after:
        return False
    if before.get("col_code") not in SENSITIVE_COLUMNS and after.get("col_code") not in SENSITIVE_COLUMNS:
        return False
    return any(before.get(field) != after.get(field) for field in SENSITIVE_ROLE_FIELDS)


def apply_metadata_change(
    db: Session,
    *,
    actor: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    action: str,
    apply: Callable[[], None],
) -> MetadataChangeLog:
    flagged = requires_second_approval(before, after)
    log = MetadataChangeLog(
        actor=actor,
        before=before,
        after=after,
        action=action,
        requires_second_approval=flagged,
        status="pending_second_approval" if flagged else "applied",
    )
    db.add(log)
    if not flagged:
        apply()
    return log
