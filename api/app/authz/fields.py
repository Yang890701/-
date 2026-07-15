from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ColumnMeta
from app.db.session import SessionLocal


def _role_allowed(role: str, roles: list[str]) -> bool:
    return role in roles


def allowed_columns(user_role: str, table_code: str, db: Session | None = None) -> set[str]:
    def load(session: Session) -> set[str]:
        columns = session.scalars(
            select(ColumnMeta)
            .where(ColumnMeta.table_code == table_code, ColumnMeta.deleted_at.is_(None))
            .order_by(ColumnMeta.id)
        ).all()
        return {column.col_code for column in columns if _role_allowed(user_role, column.read_roles)}

    if db is not None:
        return load(db)

    with SessionLocal() as session:
        return load(session)


def mask_row(row: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key in allowed}
