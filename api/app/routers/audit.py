from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.dependencies import require_roles
from app.db.models import AppUser, AuditLog
from app.db.session import get_db

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    action: str | None = None,
    table_code: str | None = None,
    ts_from: datetime | None = Query(default=None, alias="from"),
    ts_to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current_user: AppUser = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    audit_filters = {
        "action": action,
        "table_code": table_code,
        "from": ts_from.isoformat() if ts_from else None,
        "to": ts_to.isoformat() if ts_to else None,
        "page": page,
        "size": size,
    }
    db.add(AuditLog(actor=current_user.id, action="audit_query", filters=audit_filters))
    db.flush()

    statement = select(AuditLog)
    count_statement = select(func.count()).select_from(AuditLog)
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if table_code:
        conditions.append(AuditLog.table_code == table_code)
    if ts_from:
        conditions.append(AuditLog.ts >= ts_from)
    if ts_to:
        conditions.append(AuditLog.ts <= ts_to)
    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    total = db.scalar(count_statement) or 0
    rows = db.scalars(
        statement.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    db.commit()
    return {
        "rows": jsonable_encoder(
            [
                {
                    "id": row.id,
                    "actor": row.actor,
                    "action": row.action,
                    "table_code": row.table_code,
                    "filters": row.filters,
                    "row_count": row.row_count,
                    "ts": row.ts,
                }
                for row in rows
            ]
        ),
        "total": total,
        "page": page,
        "size": size,
    }
