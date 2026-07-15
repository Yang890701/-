from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import get_current_user
from app.db.models import AppUser, ColumnMeta, TableMeta
from app.db.session import get_db

router = APIRouter(prefix="/api/meta", tags=["meta"])


def _role_allowed(role: str, roles: list[str]) -> bool:
    return role in roles


@router.get("/tables")
def list_tables(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    tables = db.scalars(
        select(TableMeta).where(TableMeta.deleted_at.is_(None)).order_by(TableMeta.code)
    ).all()
    return [
        {"code": table.code, "label": table.label}
        for table in tables
        if _role_allowed(current_user.role, table.read_roles)
    ]


@router.get("/tables/{table_code}/columns")
def list_columns(
    table_code: str,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    table = db.scalar(select(TableMeta).where(TableMeta.code == table_code, TableMeta.deleted_at.is_(None)))
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown table")
    if not _role_allowed(current_user.role, table.read_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    columns = db.scalars(
        select(ColumnMeta)
        .where(ColumnMeta.table_code == table_code, ColumnMeta.deleted_at.is_(None))
        .order_by(ColumnMeta.id)
    ).all()
    return [
        {
            "code": column.col_code,
            "label": column.label,
            "type": column.type,
            "filterable": column.filterable and _role_allowed(current_user.role, column.filter_roles),
            "operators": column.operators
            if column.filterable and _role_allowed(current_user.role, column.filter_roles)
            else [],
            "exportable": _role_allowed(current_user.role, column.export_roles),
        }
        for column in columns
        if _role_allowed(current_user.role, column.read_roles)
    ]
