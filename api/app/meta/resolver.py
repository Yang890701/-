from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ColumnMeta, TableMeta


class MetadataResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedColumn:
    code: str
    physical_column: str
    type: str
    operator: str | None = None


@dataclass(frozen=True)
class ResolvedQueryPlan:
    table_code: str
    physical_table: str
    columns: list[ResolvedColumn]
    filters: list[ResolvedColumn]


def _active_table(db: Session, table_code: str) -> TableMeta:
    table = db.scalar(select(TableMeta).where(TableMeta.code == table_code, TableMeta.deleted_at.is_(None)))
    if table is None:
        raise MetadataResolutionError(f"Unregistered table: {table_code}")
    return table


def _active_columns(db: Session, table_code: str) -> dict[str, ColumnMeta]:
    columns = db.scalars(
        select(ColumnMeta).where(ColumnMeta.table_code == table_code, ColumnMeta.deleted_at.is_(None))
    ).all()
    return {column.col_code: column for column in columns}


def resolve_query_plan(
    db: Session,
    table_code: str,
    column_codes: list[str],
    filters: list[dict[str, Any]] | None = None,
) -> ResolvedQueryPlan:
    table = _active_table(db, table_code)
    columns_by_code = _active_columns(db, table_code)

    resolved_columns: list[ResolvedColumn] = []
    for column_code in column_codes:
        column = columns_by_code.get(column_code)
        if column is None:
            raise MetadataResolutionError(f"Unregistered column: {table_code}.{column_code}")
        resolved_columns.append(
            ResolvedColumn(code=column.col_code, physical_column=column.physical_column, type=column.type)
        )

    resolved_filters: list[ResolvedColumn] = []
    for item in filters or []:
        column_code = item.get("col")
        operator = item.get("op")
        column = columns_by_code.get(column_code)
        if column is None:
            raise MetadataResolutionError(f"Unregistered filter column: {table_code}.{column_code}")
        if not column.filterable:
            raise MetadataResolutionError(f"Column is not filterable: {table_code}.{column_code}")
        if operator not in column.operators:
            raise MetadataResolutionError(f"Operator not allowed: {table_code}.{column_code}.{operator}")
        resolved_filters.append(
            ResolvedColumn(
                code=column.col_code,
                physical_column=column.physical_column,
                type=column.type,
                operator=operator,
            )
        )

    return ResolvedQueryPlan(
        table_code=table.code,
        physical_table=table.physical_table,
        columns=resolved_columns,
        filters=resolved_filters,
    )
