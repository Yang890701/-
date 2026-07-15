from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.tokens import get_current_user
from app.authz.dependencies import require_roles
from app.db.models import AppUser, BillingRun, BillingRunChargeLine, BillingRunDetail, Room
from app.db.session import get_db
from app.services.billing import (
    BillingConflictError,
    BillingInputError,
    approve_billing_run,
    billing_run_summary,
    create_billing_run,
    publish_billing_run,
    reverse_billing_run,
)

router = APIRouter(tags=["billing"])

YM_PATTERN = re.compile(r"^[0-9]{6}$")


class BillingRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billing_ym: str
    scope: dict[str, Any] = Field(default_factory=lambda: {"type": "all"})
    idempotency_key: str | None = None

    @field_validator("billing_ym")
    @classmethod
    def validate_billing_ym(cls, value: str) -> str:
        if not YM_PATTERN.match(value):
            raise ValueError("billing_ym must be YYYYMM")
        month = int(value[4:6])
        if month < 1 or month > 12:
            raise ValueError("billing_ym month must be 01-12")
        return value


def _require_create_user(current_user: AppUser = Depends(get_current_user)) -> AppUser:
    if current_user.is_readonly or current_user.role not in {"admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return current_user


@router.post("/api/billing/runs", status_code=status.HTTP_201_CREATED)
def create_run(
    payload: BillingRunCreate,
    response: Response,
    current_user: AppUser = Depends(_require_create_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = create_billing_run(
            db,
            billing_ym=payload.billing_ym,
            scope=payload.scope,
            idempotency_key=payload.idempotency_key,
            created_by=current_user,
        )
    except BillingInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BillingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if not result.created:
        response.status_code = status.HTTP_200_OK
    return {"run_id": result.run.id, "status": result.run.status, "summary": result.summary}


@router.get("/api/billing/runs/{run_id}")
def get_run(
    run_id: int,
    current_user: AppUser = Depends(require_roles("accounting", "admin", "manager")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    run = _get_run_or_404(db, run_id)
    return _run_response(db, run)


@router.post("/api/billing/runs/{run_id}/approve")
def approve_run(
    run_id: int,
    current_user: AppUser = Depends(_require_create_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _get_run_or_404(db, run_id)
    try:
        run = approve_billing_run(db, run, current_user)
    except BillingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_response(db, run)


@router.post("/api/billing/runs/{run_id}/publish")
def publish_run(
    run_id: int,
    current_user: AppUser = Depends(_require_create_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _get_run_or_404(db, run_id)
    try:
        run = publish_billing_run(db, run, current_user)
    except BillingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_response(db, run)


@router.post("/api/billing/runs/{run_id}/reverse")
def reverse_run(
    run_id: int,
    current_user: AppUser = Depends(_require_create_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _get_run_or_404(db, run_id)
    try:
        run = reverse_billing_run(db, run, current_user)
    except BillingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_response(db, run)


@router.get("/api/billing/runs/{run_id}/details")
def get_run_details(
    run_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current_user: AppUser = Depends(require_roles("accounting", "admin", "manager")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del current_user
    _get_run_or_404(db, run_id)
    total = db.scalar(
        select(func.count())
        .select_from(BillingRunDetail)
        .where(BillingRunDetail.run_id == run_id, BillingRunDetail.deleted_at.is_(None))
    )
    details = db.scalars(
        select(BillingRunDetail)
        .where(BillingRunDetail.run_id == run_id, BillingRunDetail.deleted_at.is_(None))
        .order_by(BillingRunDetail.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    rows = []
    for detail in details:
        room = db.get(Room, detail.room_id)
        charge_lines = db.scalars(
            select(BillingRunChargeLine)
            .where(
                BillingRunChargeLine.detail_id == detail.id,
                BillingRunChargeLine.deleted_at.is_(None),
            )
            .order_by(BillingRunChargeLine.id.asc())
        ).all()
        rows.append(
            {
                "detail_id": detail.id,
                "room_id": detail.room_id,
                "room_code": room.room_code if room is not None else None,
                "subtotal": detail.subtotal,
                "status": detail.status,
                "charge_lines": [
                    {
                        "id": line.id,
                        "charge_type": line.charge_type,
                        "amount": line.amount,
                        "source_ref": line.source_ref,
                    }
                    for line in charge_lines
                ],
            }
        )

    return jsonable_encoder({"rows": rows, "total": total or 0, "page": page, "size": size})


def _get_run_or_404(db: Session, run_id: int) -> BillingRun:
    run = db.scalar(select(BillingRun).where(BillingRun.id == run_id, BillingRun.deleted_at.is_(None)))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing run not found")
    return run


def _run_response(db: Session, run: BillingRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "billing_ym": run.billing_ym,
        "scope": run.scope,
        "version": run.version,
        "status": run.status,
        "summary": billing_run_summary(db, run),
    }
