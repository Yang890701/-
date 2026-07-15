from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.tokens import get_current_user
from app.db.models import AppUser, AuditLog, ColumnMeta, Meter, Room, Site
from app.db.session import get_db

router = APIRouter(prefix="/api/master", tags=["master"])

WRITE_ROLES = {"admin", "manager"}


class SitePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_code: str
    name: str | None = None
    address: str | None = None
    management_unit: str | None = None


class MeterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    electricity_code: str
    name: str | None = None
    management_type: str | None = None
    note: str | None = None


class RoomPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: int
    room_code: str
    room_name: str | None = None
    meter_id: int | None = None
    management_type: str | None = None
    management_contact: str | None = None
    billing_mode: str | None = None


class SiteResponse(SitePayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class MeterResponse(MeterPayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class RoomResponse(RoomPayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class MasterConfig:
    model: type[Site] | type[Meter] | type[Room]
    payload_model: type[SitePayload] | type[MeterPayload] | type[RoomPayload]
    response_model: type[SiteResponse] | type[MeterResponse] | type[RoomResponse]
    writable_columns: set[str]


MASTER_TABLES: dict[str, MasterConfig] = {
    "site": MasterConfig(
        model=Site,
        payload_model=SitePayload,
        response_model=SiteResponse,
        writable_columns={"site_code", "name", "address", "management_unit"},
    ),
    "meter": MasterConfig(
        model=Meter,
        payload_model=MeterPayload,
        response_model=MeterResponse,
        writable_columns={"electricity_code", "name", "management_type", "note"},
    ),
    "room": MasterConfig(
        model=Room,
        payload_model=RoomPayload,
        response_model=RoomResponse,
        writable_columns={
            "site_id",
            "room_code",
            "room_name",
            "meter_id",
            "management_type",
            "management_contact",
            "billing_mode",
        },
    ),
}


def _master_config(table_code: str) -> MasterConfig:
    config = MASTER_TABLES.get(table_code)
    if config is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported master table")
    return config


def _require_master_write_role(user: AppUser) -> None:
    if user.is_readonly or user.role not in WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _check_field_write_roles(db: Session, table_code: str, field_names: set[str], role: str) -> None:
    columns = db.scalars(
        select(ColumnMeta).where(
            ColumnMeta.table_code == table_code,
            ColumnMeta.col_code.in_(field_names),
            ColumnMeta.deleted_at.is_(None),
        )
    ).all()
    columns_by_code = {column.col_code: column for column in columns}
    missing = field_names - set(columns_by_code)
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unregistered writable column")
    for column in columns:
        if role not in column.write_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Column is not writable")


def _parse_payload(config: MasterConfig, body: dict[str, Any]) -> SitePayload | MeterPayload | RoomPayload:
    try:
        return config.payload_model.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


def _active_by_id(db: Session, model: type[Site] | type[Meter] | type[Room], row_id: int):
    return db.scalar(select(model).where(model.id == row_id, model.deleted_at.is_(None)))


def _get_active_row(db: Session, config: MasterConfig, row_id: int):
    row = _active_by_id(db, config.model, row_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Master row not found")
    return row


def _validate_room_foreign_keys(db: Session, payload: RoomPayload) -> None:
    if _active_by_id(db, Site, payload.site_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id must reference an active site")
    if payload.meter_id is not None and _active_by_id(db, Meter, payload.meter_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="meter_id must reference an active meter")


def _validate_foreign_keys(db: Session, table_code: str, payload: SitePayload | MeterPayload | RoomPayload) -> None:
    if table_code == "room":
        _validate_room_foreign_keys(db, payload)  # type: ignore[arg-type]


def _reject_duplicate_natural_key(
    db: Session,
    table_code: str,
    payload: SitePayload | MeterPayload | RoomPayload,
    *,
    existing_id: int | None = None,
) -> None:
    if table_code == "site":
        statement = select(Site.id).where(
            Site.site_code == payload.site_code,  # type: ignore[union-attr]
            Site.deleted_at.is_(None),
        )
    elif table_code == "meter":
        statement = select(Meter.id).where(
            Meter.electricity_code == payload.electricity_code,  # type: ignore[union-attr]
            Meter.deleted_at.is_(None),
        )
    elif table_code == "room":
        statement = select(Room.id).where(
            Room.site_id == payload.site_id,  # type: ignore[union-attr]
            Room.room_code == payload.room_code,  # type: ignore[union-attr]
            Room.deleted_at.is_(None),
        )
    else:
        return
    if existing_id is not None:
        statement = statement.where(_model_id_column(table_code) != existing_id)
    if db.scalar(statement) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="自然鍵重複")


def _model_id_column(table_code: str):
    return _master_config(table_code).model.id


def _write_audit(db: Session, user: AppUser, action: str, table_code: str, filters: dict[str, Any]) -> None:
    db.add(
        AuditLog(
            actor=user.id,
            action=action,
            table_code=table_code,
            filters=filters,
            row_count=1,
        )
    )


def _flush_or_conflict(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="自然鍵重複") from exc


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="自然鍵重複") from exc


def _refresh_and_encode(
    db: Session,
    config: MasterConfig,
    row: Site | Meter | Room,
) -> dict[str, Any]:
    db.refresh(row)
    return jsonable_encoder(config.response_model.model_validate(row))


@router.get("/{table_code}")
def list_master(
    table_code: str,
    include_inactive: bool = Query(default=False),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    config = _master_config(table_code)
    statement = select(config.model).order_by(config.model.id.asc())
    if not include_inactive:
        statement = statement.where(config.model.deleted_at.is_(None))
    rows = db.scalars(statement).all()
    return {
        "rows": jsonable_encoder([config.response_model.model_validate(row) for row in rows]),
        "total": len(rows),
    }


@router.post("/{table_code}", status_code=status.HTTP_201_CREATED)
def create_master(
    table_code: str,
    body: dict[str, Any],
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = _master_config(table_code)
    _require_master_write_role(current_user)
    payload = _parse_payload(config, body)
    payload_data = payload.model_dump()
    _check_field_write_roles(db, table_code, set(payload_data), current_user.role)
    _validate_foreign_keys(db, table_code, payload)
    _reject_duplicate_natural_key(db, table_code, payload)

    row = config.model(**payload_data)
    db.add(row)
    _flush_or_conflict(db)
    _write_audit(db, current_user, "master_create", table_code, {"id": row.id})
    _commit_or_conflict(db)
    return _refresh_and_encode(db, config, row)


@router.put("/{table_code}/{row_id}")
def update_master(
    table_code: str,
    row_id: int,
    body: dict[str, Any],
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = _master_config(table_code)
    _require_master_write_role(current_user)
    row = _get_active_row(db, config, row_id)
    payload = _parse_payload(config, body)
    payload_data = payload.model_dump()
    _check_field_write_roles(db, table_code, set(payload_data), current_user.role)
    _validate_foreign_keys(db, table_code, payload)
    _reject_duplicate_natural_key(db, table_code, payload, existing_id=row_id)

    for key, value in payload_data.items():
        setattr(row, key, value)
    _write_audit(db, current_user, "master_update", table_code, {"id": row_id})
    _commit_or_conflict(db)
    return _refresh_and_encode(db, config, row)


@router.delete("/{table_code}/{row_id}")
def delete_master(
    table_code: str,
    row_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = _master_config(table_code)
    _require_master_write_role(current_user)
    _check_field_write_roles(db, table_code, config.writable_columns, current_user.role)
    row = _get_active_row(db, config, row_id)
    row.deleted_at = datetime.now(UTC)
    _write_audit(db, current_user, "master_delete", table_code, {"id": row_id})
    _commit_or_conflict(db)
    return _refresh_and_encode(db, config, row)
