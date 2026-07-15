from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.tokens import get_current_user
from app.db.models import (
    AppUser,
    Attachment,
    AuditLog,
    AvgPrice,
    Meter,
    MeterEvent,
    MeterReading,
    ReadingException,
    Room,
    RoomMeterAssignment,
)
from app.db.session import get_db

router = APIRouter(tags=["meter"])

WRITE_ROLES = {"admin", "manager"}
YM_PATTERN = re.compile(r"^[0-9]{6}$")


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: int
    meter_id: int
    meter_category: str = Field(min_length=1)
    effective_from_ym: str
    initial_reading: int | None = None

    @field_validator("effective_from_ym")
    @classmethod
    def validate_effective_from_ym(cls, value: str) -> str:
        return _validate_ym_value(value)


class ChangeMeterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_meter_id: int
    event_ym: str
    final_reading: int
    new_initial_reading: int

    @field_validator("event_ym")
    @classmethod
    def validate_event_ym(cls, value: str) -> str:
        return _validate_ym_value(value)


class MeterReadingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: int
    billing_ym: str
    reading_kind: str = Field(min_length=1)
    reading: int | None = None
    attachment_id: int | None = None
    note: str | None = None

    @field_validator("billing_ym")
    @classmethod
    def validate_billing_ym(cls, value: str) -> str:
        return _validate_ym_value(value)


class AvgPriceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meter_id: int
    billing_ym: str
    price: Decimal
    attachment_id: int | None = None

    @field_validator("billing_ym")
    @classmethod
    def validate_billing_ym(cls, value: str) -> str:
        return _validate_ym_value(value)


def _validate_ym_value(value: str) -> str:
    if not YM_PATTERN.match(value):
        raise ValueError("billing period must be YYYYMM")
    month = int(value[4:6])
    if month < 1 or month > 12:
        raise ValueError("billing period month must be 01-12")
    return value


def _previous_ym(value: str) -> str:
    year = int(value[:4])
    month = int(value[4:6])
    if month == 1:
        return f"{year - 1}12"
    return f"{year}{month - 1:02d}"


def _require_write_role(user: AppUser) -> None:
    if user.is_readonly or user.role not in WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _active_by_id(db: Session, model: type[Room] | type[Meter] | type[RoomMeterAssignment], row_id: int):
    return db.scalar(select(model).where(model.id == row_id, model.deleted_at.is_(None)))


def _validate_room_and_meter(db: Session, room_id: int, meter_id: int) -> None:
    if _active_by_id(db, Room, room_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="room_id must reference an active room")
    if _active_by_id(db, Meter, meter_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="meter_id must reference an active meter")


def _validate_meter(db: Session, meter_id: int) -> None:
    if _active_by_id(db, Meter, meter_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="meter_id must reference an active meter")


def _validate_attachment(db: Session, attachment_id: int | None) -> None:
    if attachment_id is None:
        return
    attachment = db.scalar(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.deleted_at.is_(None))
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="attachment_id must reference an active attachment",
        )


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


def _flush_or_conflict(db: Session, detail: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc


def _assignment_to_dict(row: RoomMeterAssignment) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row.id,
            "room_id": row.room_id,
            "meter_id": row.meter_id,
            "effective_from_ym": row.effective_from_ym,
            "effective_to_ym": row.effective_to_ym,
            "initial_reading": row.initial_reading,
            "final_reading": row.final_reading,
            "meter_category": row.meter_category,
            "meter_category_id": row.meter_category_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        }
    )


def _reading_to_dict(row: MeterReading) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row.id,
            "assignment_id": row.assignment_id,
            "billing_ym": row.billing_ym,
            "reading_kind": row.reading_kind,
            "reading": row.reading,
            "attachment_id": row.attachment_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        }
    )


def _exception_to_dict(row: ReadingException) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row.id,
            "assignment_id": row.assignment_id,
            "billing_ym": row.billing_ym,
            "reason": row.reason,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        }
    )


def _avg_price_to_dict(row: AvgPrice) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row.id,
            "meter_id": row.meter_id,
            "billing_ym": row.billing_ym,
            "price": str(row.price),
            "attachment_id": row.attachment_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        }
    )


def _get_assignment(db: Session, assignment_id: int) -> RoomMeterAssignment:
    assignment = _active_by_id(db, RoomMeterAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignment_id must reference an active assignment")
    return assignment


def _prior_reading(db: Session, assignment_id: int, billing_ym: str) -> MeterReading | None:
    prior_ym = _previous_ym(billing_ym)
    return db.scalar(
        select(MeterReading)
        .where(
            MeterReading.assignment_id == assignment_id,
            MeterReading.billing_ym == prior_ym,
            MeterReading.deleted_at.is_(None),
        )
        .order_by(MeterReading.id.desc())
    )


def _make_reading_exception(
    db: Session,
    user: AppUser,
    payload: MeterReadingCreate,
    reason: str,
) -> dict[str, Any]:
    exception = ReadingException(
        assignment_id=payload.assignment_id,
        billing_ym=payload.billing_ym,
        reason=reason,
    )
    db.add(exception)
    _flush_or_conflict(db, "Duplicate reading exception")
    _write_audit(
        db,
        user,
        "reading_exception_create",
        "reading_exception",
        {"assignment_id": payload.assignment_id, "billing_ym": payload.billing_ym},
    )
    _commit_or_conflict(db, "Duplicate reading exception")
    db.refresh(exception)
    return {"kind": "reading_exception", "row": _exception_to_dict(exception)}


@router.post("/api/meter-assignments", status_code=status.HTTP_201_CREATED)
def create_meter_assignment(
    payload: AssignmentCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_write_role(current_user)
    _validate_room_and_meter(db, payload.room_id, payload.meter_id)
    assignment = RoomMeterAssignment(
        room_id=payload.room_id,
        meter_id=payload.meter_id,
        effective_from_ym=payload.effective_from_ym,
        initial_reading=payload.initial_reading,
        meter_category=payload.meter_category,
    )
    db.add(assignment)
    _flush_or_conflict(db, "Meter assignment overlaps an active range for this room and category")
    _write_audit(
        db,
        current_user,
        "meter_assignment_create",
        "room_meter_assignment",
        {"id": assignment.id},
    )
    _commit_or_conflict(db, "Meter assignment overlaps an active range for this room and category")
    db.refresh(assignment)
    return _assignment_to_dict(assignment)


@router.get("/api/meter-assignments")
def list_meter_assignments(
    room_id: int | None = Query(default=None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    statement = select(RoomMeterAssignment).where(RoomMeterAssignment.deleted_at.is_(None))
    if room_id is not None:
        statement = statement.where(RoomMeterAssignment.room_id == room_id)
    rows = db.scalars(statement.order_by(RoomMeterAssignment.id.asc())).all()
    return {"rows": [_assignment_to_dict(row) for row in rows], "total": len(rows)}


@router.post("/api/meter-assignments/{assignment_id}/change-meter", status_code=status.HTTP_201_CREATED)
def change_meter(
    assignment_id: int,
    payload: ChangeMeterRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_write_role(current_user)
    assignment = _get_assignment(db, assignment_id)
    _validate_meter(db, payload.new_meter_id)
    if payload.event_ym <= assignment.effective_from_ym:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_ym must be after the assignment effective_from_ym",
        )

    assignment.effective_to_ym = _previous_ym(payload.event_ym)
    assignment.final_reading = payload.final_reading
    new_assignment = RoomMeterAssignment(
        room_id=assignment.room_id,
        meter_id=payload.new_meter_id,
        effective_from_ym=payload.event_ym,
        initial_reading=payload.new_initial_reading,
        meter_category=assignment.meter_category,
        meter_category_id=assignment.meter_category_id,
    )
    event = MeterEvent(
        assignment_id=assignment.id,
        event_type="換表",
        event_ym=payload.event_ym,
        old_reading=payload.final_reading,
        new_reading=payload.new_initial_reading,
    )
    db.add_all([new_assignment, event])
    _flush_or_conflict(db, "Meter assignment overlaps an active range for this room and category")
    _write_audit(
        db,
        current_user,
        "meter_assignment_change",
        "room_meter_assignment",
        {"old_assignment_id": assignment.id, "new_assignment_id": new_assignment.id},
    )
    _commit_or_conflict(db, "Meter assignment overlaps an active range for this room and category")
    db.refresh(assignment)
    db.refresh(new_assignment)
    db.refresh(event)
    return {
        "old_assignment": _assignment_to_dict(assignment),
        "new_assignment": _assignment_to_dict(new_assignment),
        "event": jsonable_encoder(
            {
                "id": event.id,
                "assignment_id": event.assignment_id,
                "event_type": event.event_type,
                "event_ym": event.event_ym,
                "old_reading": event.old_reading,
                "new_reading": event.new_reading,
            }
        ),
    }


@router.post("/api/meter-readings", status_code=status.HTTP_201_CREATED)
def create_meter_reading(
    payload: MeterReadingCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_write_role(current_user)
    assignment = _get_assignment(db, payload.assignment_id)
    _validate_attachment(db, payload.attachment_id)

    if payload.reading is None:
        reason = payload.note or "missing reading"
        return _make_reading_exception(db, current_user, payload, reason)

    prior = _prior_reading(db, payload.assignment_id, payload.billing_ym)
    is_initial_period = payload.billing_ym == assignment.effective_from_ym
    if payload.reading_kind == "例行" and not is_initial_period and prior is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="須先傳前期讀數 before uploading a routine reading",
        )

    baseline = prior.reading if prior is not None else assignment.initial_reading if is_initial_period else None
    if baseline is not None and payload.reading < baseline:
        return _make_reading_exception(
            db,
            current_user,
            payload,
            f"negative usage: reading {payload.reading} is below prior reading {baseline}",
        )

    reading = MeterReading(
        assignment_id=payload.assignment_id,
        billing_ym=payload.billing_ym,
        reading_kind=payload.reading_kind,
        reading=payload.reading,
        attachment_id=payload.attachment_id,
    )
    db.add(reading)
    _flush_or_conflict(db, "Duplicate meter reading")
    _write_audit(
        db,
        current_user,
        "meter_reading_create",
        "meter_reading",
        {"assignment_id": payload.assignment_id, "billing_ym": payload.billing_ym},
    )
    _commit_or_conflict(db, "Duplicate meter reading")
    db.refresh(reading)
    return {"kind": "meter_reading", "row": _reading_to_dict(reading)}


@router.get("/api/meter-readings")
def list_meter_readings(
    assignment_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    rows = db.scalars(
        select(MeterReading)
        .where(MeterReading.assignment_id == assignment_id, MeterReading.deleted_at.is_(None))
        .order_by(MeterReading.billing_ym.desc(), MeterReading.id.desc())
    ).all()
    return {"rows": [_reading_to_dict(row) for row in rows], "total": len(rows)}


@router.get("/api/reading-exceptions")
def list_reading_exceptions(
    exception_status: str = Query(default="open", alias="status"),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    rows = db.scalars(
        select(ReadingException)
        .where(ReadingException.status == exception_status, ReadingException.deleted_at.is_(None))
        .order_by(ReadingException.created_at.desc(), ReadingException.id.desc())
    ).all()
    return {"rows": [_exception_to_dict(row) for row in rows], "total": len(rows)}


@router.post("/api/avg-prices", status_code=status.HTTP_201_CREATED)
def create_avg_price(
    payload: AvgPriceCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_write_role(current_user)
    _validate_meter(db, payload.meter_id)
    _validate_attachment(db, payload.attachment_id)
    existing = db.scalar(
        select(AvgPrice.id).where(
            AvgPrice.meter_id == payload.meter_id,
            AvgPrice.billing_ym == payload.billing_ym,
            AvgPrice.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate average price")

    avg_price = AvgPrice(
        meter_id=payload.meter_id,
        billing_ym=payload.billing_ym,
        price=payload.price,
        attachment_id=payload.attachment_id,
    )
    db.add(avg_price)
    _flush_or_conflict(db, "Duplicate average price")
    _write_audit(
        db,
        current_user,
        "avg_price_create",
        "avg_price",
        {"meter_id": payload.meter_id, "billing_ym": payload.billing_ym},
    )
    _commit_or_conflict(db, "Duplicate average price")
    db.refresh(avg_price)
    return _avg_price_to_dict(avg_price)


@router.get("/api/avg-prices")
def list_avg_prices(
    meter_id: int | None = Query(default=None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    statement = select(AvgPrice).where(AvgPrice.deleted_at.is_(None))
    if meter_id is not None:
        statement = statement.where(AvgPrice.meter_id == meter_id)
    rows = db.scalars(statement.order_by(AvgPrice.billing_ym.desc(), AvgPrice.id.desc())).all()
    return {"rows": [_avg_price_to_dict(row) for row in rows], "total": len(rows)}
