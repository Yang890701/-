from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AppUser,
    AuditLog,
    AvgPrice,
    BillingRun,
    BillingRunChargeLine,
    BillingRunDetail,
    ExceptionCharge,
    MeterReading,
    ReadingException,
    RentConfirm,
    Room,
    RoomFixedFee,
    RoomMeterAssignment,
    Site,
    SpecialPrice,
    TenantContract,
)

YM_PATTERN = re.compile(r"^[0-9]{6}$")
TRAILING_ROOM_NUMBER = re.compile(r"(\d{3})$")

ELECTRICITY_CHARGE_TYPE = "電費"
MONTHLY_RENT_CONFIRM_CHARGE_TYPE = "月結"
PUBLISHED_RENT_CONFIRM_STATUS = "已確認"
REVERSAL_RENT_CONFIRM_CHARGE_TYPE = "沖銷"
REVERSAL_RENT_CONFIRM_STATUS = "作廢"
TAIPOWER_CHARGE_TYPES = {"台電", "台電帳單", "taipower", "taipower_bill", "tai_power_bill"}

NORMAL_MODES = {"", "normal", "一般", "一般電價"}
SPECIAL_PRICE_MODES = {"special_price", "fixed", "fixed_price", "特殊", "特殊電價", "固定", "固定電價", "固定/特殊電價"}
JINGPING_MERGE_MODES = {
    "jingping_merge",
    "jingping_401_404_merge",
    "景平401-404合併",
    "景平 401-404 合併",
}
TOTAL_SUB_MODES = {"total_sub", "total_sub_meter", "total_and_sub", "總電表與子電表", "總電表子電表"}
TOTAL_BILL_SPLIT_MODES = {"total_bill_split", "total_bill", "總電費拆帳"}

TOTAL_ALIASES = {"total", "main_total", "total_meter", "總電表", "總表"}
SUB_ALIASES = {"sub", "sub_meter", "child", "子電表", "子表"}
MAIN_ALIASES = {"main", "normal", "primary", "routine", "電表", "主表"}


class BillingConflictError(Exception):
    """Raised when a run cannot be created because the idempotency/lock boundary blocks it."""


class BillingInputError(ValueError):
    """Raised when billing input shape is invalid."""


@dataclass(frozen=True)
class UsageResult:
    assignment_id: int
    meter_id: int
    meter_category: str
    reading_kind: str | None
    current_reading_id: int
    prior_reading_id: int | None
    current_reading: int
    prior_reading: int
    usage: int


@dataclass(frozen=True)
class RoomCalculation:
    room_id: int
    room_code: str
    site_id: int
    mode: str
    status: str
    subtotal: int | None
    reason: str | None
    source_ref: dict[str, Any] | None
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class BillingRunResult:
    run: BillingRun
    summary: dict[str, Any]
    created: bool


def validate_billing_ym(value: str) -> str:
    if not YM_PATTERN.match(value):
        raise BillingInputError("billing_ym must be YYYYMM")
    month = int(value[4:6])
    if month < 1 or month > 12:
        raise BillingInputError("billing_ym month must be 01-12")
    return value


def previous_ym(value: str) -> str:
    year = int(value[:4])
    month = int(value[4:6])
    if month == 1:
        return f"{year - 1}12"
    return f"{year}{month - 1:02d}"


def canonicalize_scope(scope: dict[str, Any] | None) -> dict[str, Any]:
    if not scope or scope.get("type") == "all":
        return {"type": "all"}
    if "site_id" in scope:
        return {"site_ids": [int(scope["site_id"])]}
    if "site_ids" in scope:
        site_ids = sorted({int(value) for value in scope["site_ids"]})
        if not site_ids:
            raise BillingInputError("scope.site_ids must not be empty")
        return {"site_ids": site_ids}
    if "room_id" in scope:
        return {"room_ids": [int(scope["room_id"])]}
    if "room_ids" in scope:
        room_ids = sorted({int(value) for value in scope["room_ids"]})
        if not room_ids:
            raise BillingInputError("scope.room_ids must not be empty")
        return {"room_ids": room_ids}
    if "management_unit" in scope:
        value = str(scope["management_unit"]).strip()
        if not value:
            raise BillingInputError("scope.management_unit must not be empty")
        return {"management_unit": value}
    raise BillingInputError("scope must be all, site_id/site_ids, room_id/room_ids, or management_unit")


def scope_key(billing_ym: str, scope: dict[str, Any]) -> str:
    return f"{billing_ym}:{json.dumps(scope, sort_keys=True, separators=(',', ':'))}"


def summarize_calculations(calculations: list[RoomCalculation]) -> dict[str, Any]:
    by_site: dict[int, dict[str, Any]] = {}
    for calculation in calculations:
        bucket = by_site.setdefault(
            calculation.site_id,
            {"site_id": calculation.site_id, "total_amount": 0, "calculated": 0, "skipped": 0},
        )
        if calculation.status == "calculated" and calculation.subtotal is not None:
            bucket["total_amount"] += calculation.subtotal
            bucket["calculated"] += 1
        else:
            bucket["skipped"] += 1

    calculated = sum(1 for calculation in calculations if calculation.status == "calculated")
    skipped = len(calculations) - calculated
    return {
        "total_rooms": len(calculations),
        "calculated": calculated,
        "skipped": skipped,
        "total_amount": sum(calculation.subtotal or 0 for calculation in calculations),
        "by_site": [by_site[site_id] for site_id in sorted(by_site)],
    }


def compute_golden_case(input_data: dict[str, Any]) -> dict[str, int]:
    mode = _normalize_mode(input_data.get("mode"))
    if mode == "normal":
        usage = _usage_from_golden(input_data)
        amount = _round_ntd(Decimal(usage) * _decimal(input_data["avg_price"]))
    elif mode == "special_price":
        usage = _usage_from_golden(input_data)
        amount = _round_ntd(Decimal(usage) * _decimal(input_data["special_price"]))
    elif mode == "jingping_merge":
        usage = sum(_usage_from_golden(component) for component in input_data["components"])
        amount = _round_ntd(Decimal(usage) * _decimal(input_data["avg_price"]))
    elif mode == "total_sub":
        total_usage = _usage_from_golden(input_data["total"])
        sub_usage = _usage_from_golden(input_data["sub"])
        amount = _round_ntd(Decimal(total_usage - sub_usage) * _decimal(input_data["avg_price"]))
    elif mode == "total_bill_split":
        child_total = sum(int(value) for value in input_data["child_electricity_amounts"])
        amount = int(input_data["taipower_bill_total"]) - child_total
    else:
        raise BillingInputError(f"unsupported golden case mode: {input_data.get('mode')}")
    return {"electricity_amount": amount}


def preview_billing_run(
    db: Session,
    *,
    billing_ym: str,
    scope: dict[str, Any] | None,
    write_exceptions: bool = False,
) -> tuple[list[RoomCalculation], dict[str, Any]]:
    billing_ym = validate_billing_ym(billing_ym)
    canonical_scope = canonicalize_scope(scope)
    rooms = _rooms_for_scope(db, canonical_scope)

    calculations: list[RoomCalculation] = []
    calculated_by_room: dict[int, RoomCalculation] = {}
    split_rooms: list[Room] = []

    for room in rooms:
        mode = _normalize_mode(room.billing_mode)
        if mode == "total_bill_split":
            split_rooms.append(room)
            continue
        calculation = _calculate_non_split_room(
            db,
            room=room,
            billing_ym=billing_ym,
            mode=mode,
            write_exceptions=write_exceptions,
        )
        calculations.append(calculation)
        calculated_by_room[room.id] = calculation

    for room in split_rooms:
        calculation = _calculate_total_bill_split_room(
            db,
            room=room,
            billing_ym=billing_ym,
            calculated_by_room=calculated_by_room,
        )
        calculations.append(calculation)
        calculated_by_room[room.id] = calculation

    summary = summarize_calculations(calculations)
    return calculations, {
        "billing_ym": billing_ym,
        "scope": canonical_scope,
        "rooms": [asdict(calculation) for calculation in calculations],
        "summary": summary,
    }


def create_billing_run(
    db: Session,
    *,
    billing_ym: str,
    scope: dict[str, Any] | None,
    idempotency_key: str | None,
    created_by: AppUser,
) -> BillingRunResult:
    billing_ym = validate_billing_ym(billing_ym)
    canonical_scope = canonicalize_scope(scope)

    if idempotency_key:
        existing_by_key = db.scalar(
            select(BillingRun).where(
                BillingRun.idempotency_key == idempotency_key,
                BillingRun.deleted_at.is_(None),
            )
        )
        if existing_by_key is not None:
            return BillingRunResult(
                run=existing_by_key,
                summary=billing_run_summary(db, existing_by_key),
                created=False,
            )

    lock_name = f"billing-run:{scope_key(billing_ym, canonical_scope)}"
    if not _try_advisory_xact_lock(db, lock_name):
        raise BillingConflictError("billing run is already in progress for this billing_ym and scope")

    existing_for_scope = db.scalar(
        select(BillingRun).where(
            BillingRun.billing_ym == billing_ym,
            BillingRun.scope == canonical_scope,
            BillingRun.status != "reversed",
            BillingRun.deleted_at.is_(None),
        )
    )
    if existing_for_scope is not None:
        raise BillingConflictError("billing run already exists for this billing_ym and scope")

    _advisory_xact_lock(db, f"billing-run-version:{billing_ym}")
    version = (
        db.scalar(
            select(func.max(BillingRun.version)).where(
                BillingRun.billing_ym == billing_ym,
                BillingRun.deleted_at.is_(None),
            )
        )
        or 0
    ) + 1

    run_key = idempotency_key or f"auto:{uuid4()}"
    calculations, snapshot = preview_billing_run(
        db,
        billing_ym=billing_ym,
        scope=canonical_scope,
        write_exceptions=True,
    )
    run = BillingRun(
        billing_ym=billing_ym,
        version=version,
        scope=canonical_scope,
        status="calculated",
        idempotency_key=run_key,
        input_snapshot=snapshot,
        created_by=created_by.id,
    )
    db.add(run)
    try:
        db.flush()
        for calculation in calculations:
            detail = BillingRunDetail(
                run_id=run.id,
                room_id=calculation.room_id,
                subtotal=calculation.subtotal,
                status=calculation.status,
            )
            db.add(detail)
            db.flush()
            if calculation.status == "calculated" and calculation.subtotal is not None:
                db.add(
                    BillingRunChargeLine(
                        detail_id=detail.id,
                        charge_type=ELECTRICITY_CHARGE_TYPE,
                        amount=calculation.subtotal,
                        source_ref=calculation.source_ref,
                    )
                )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BillingConflictError("billing run could not be created because of a duplicate key") from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(run)
    return BillingRunResult(run=run, summary=snapshot["summary"], created=True)


def approve_billing_run(db: Session, run: BillingRun, actor: AppUser) -> BillingRun:
    if run.status != "calculated":
        raise BillingConflictError("billing run must be calculated before approval")

    run.status = "approved"
    _write_billing_audit(db, actor, "billing_run_approve", run, row_count=1)
    _commit_billing_transition(db, "billing run could not be approved because of a duplicate key")
    db.refresh(run)
    return run


def publish_billing_run(db: Session, run: BillingRun, actor: AppUser) -> BillingRun:
    if run.status == "published":
        raise BillingConflictError("billing run is already published")
    if run.status != "approved":
        raise BillingConflictError("billing run must be approved before publish")

    details = _run_details(db, run.id)
    for detail in details:
        components = _published_rent_confirm_components(db, run, detail)
        db.add(
            RentConfirm(
                room_id=detail.room_id,
                billing_ym=run.billing_ym,
                charge_type=MONTHLY_RENT_CONFIRM_CHARGE_TYPE,
                run_version=run.version,
                status=PUBLISHED_RENT_CONFIRM_STATUS,
                rent_amount=components["rent_amount"],
                electricity_amount=components["electricity_amount"],
                fixed_fee_amount=components["fixed_fee_amount"],
                exception_amount=components["exception_amount"],
                total_amount=components["total_amount"],
                amounts=components["amounts"],
            )
        )

    run.status = "published"
    _write_billing_audit(db, actor, "billing_run_publish", run, row_count=len(details))
    _commit_billing_transition(db, "billing run is already published")
    db.refresh(run)
    return run


def reverse_billing_run(db: Session, run: BillingRun, actor: AppUser) -> BillingRun:
    if run.status != "published":
        raise BillingConflictError("billing run must be published before reversal")

    originals = db.scalars(
        select(RentConfirm)
        .where(
            RentConfirm.billing_ym == run.billing_ym,
            RentConfirm.charge_type == MONTHLY_RENT_CONFIRM_CHARGE_TYPE,
            RentConfirm.run_version == run.version,
            RentConfirm.status == PUBLISHED_RENT_CONFIRM_STATUS,
            RentConfirm.deleted_at.is_(None),
        )
        .order_by(RentConfirm.room_id.asc(), RentConfirm.id.asc())
    ).all()

    for original in originals:
        rent_amount = _negate_amount(original.rent_amount)
        electricity_amount = _negate_amount(original.electricity_amount)
        fixed_fee_amount = _negate_amount(original.fixed_fee_amount)
        exception_amount = _negate_amount(original.exception_amount)
        total_amount = _negate_amount(original.total_amount)
        db.add(
            RentConfirm(
                room_id=original.room_id,
                billing_ym=original.billing_ym,
                charge_type=REVERSAL_RENT_CONFIRM_CHARGE_TYPE,
                run_version=run.version,
                status=REVERSAL_RENT_CONFIRM_STATUS,
                rent_amount=rent_amount,
                electricity_amount=electricity_amount,
                fixed_fee_amount=fixed_fee_amount,
                exception_amount=exception_amount,
                total_amount=total_amount,
                amounts={
                    "reversal_of": {
                        "rent_confirm_id": original.id,
                        "charge_type": original.charge_type,
                        "run_version": original.run_version,
                    },
                    "rent_amount": rent_amount,
                    "electricity_amount": electricity_amount,
                    "fixed_fee_amount": fixed_fee_amount,
                    "exception_amount": exception_amount,
                    "total_amount": total_amount,
                },
            )
        )

    run.status = "reversed"
    _write_billing_audit(db, actor, "billing_run_reverse", run, row_count=len(originals))
    _commit_billing_transition(db, "billing run reversal already exists")
    db.refresh(run)
    return run


def billing_run_summary(db: Session, run: BillingRun) -> dict[str, Any]:
    if isinstance(run.input_snapshot, dict) and isinstance(run.input_snapshot.get("summary"), dict):
        return run.input_snapshot["summary"]

    details = db.scalars(
        select(BillingRunDetail).where(BillingRunDetail.run_id == run.id, BillingRunDetail.deleted_at.is_(None))
    ).all()
    calculations = []
    for detail in details:
        room = db.get(Room, detail.room_id)
        if room is None:
            continue
        calculations.append(
            RoomCalculation(
                room_id=room.id,
                room_code=room.room_code,
                site_id=room.site_id,
                mode=_normalize_mode(room.billing_mode),
                status=detail.status or "skipped",
                subtotal=detail.subtotal,
                reason=None,
                source_ref=None,
                snapshot={},
            )
        )
    return summarize_calculations(calculations)


def reconciliation_report(db: Session, billing_ym: str, scope: dict[str, Any] | None = None) -> dict[str, Any]:
    calculations, _snapshot = preview_billing_run(db, billing_ym=billing_ym, scope=scope, write_exceptions=False)
    computed_by_room = {
        calculation.room_id: calculation.subtotal
        for calculation in calculations
        if calculation.status == "calculated" and calculation.subtotal is not None
    }
    expected_by_room = _latest_rent_confirm_amounts(db, billing_ym)
    room_ids = sorted(set(computed_by_room) | set(expected_by_room))

    mismatches: list[dict[str, Any]] = []
    matched = 0
    per_site: dict[int, dict[str, Any]] = {}
    for room_id in room_ids:
        room = db.get(Room, room_id)
        if room is None:
            continue
        computed = computed_by_room.get(room_id)
        expected = expected_by_room.get(room_id)
        diff = None if computed is None or expected is None else computed - expected
        site_bucket = per_site.setdefault(
            room.site_id,
            {"site_id": room.site_id, "computed_total": 0, "expected_total": 0},
        )
        site_bucket["computed_total"] += computed or 0
        site_bucket["expected_total"] += expected or 0
        if diff is not None and abs(diff) <= 1:
            matched += 1
        else:
            mismatches.append(
                {
                    "room_id": room_id,
                    "room_code": room.room_code,
                    "computed": computed,
                    "expected": expected,
                    "diff": diff,
                }
            )

    return {
        "billing_ym": billing_ym,
        "total_rooms": len(room_ids),
        "matched": matched,
        "mismatched": len(mismatches),
        "mismatches": mismatches,
        "per_site": [per_site[site_id] for site_id in sorted(per_site)],
        "overall": {
            "computed_total": sum(value or 0 for value in computed_by_room.values()),
            "expected_total": sum(value or 0 for value in expected_by_room.values()),
        },
    }


def _write_billing_audit(
    db: Session,
    actor: AppUser,
    action: str,
    run: BillingRun,
    *,
    row_count: int,
) -> None:
    db.add(
        AuditLog(
            actor=actor.id,
            action=action,
            table_code="billing_run",
            filters={"run_id": run.id, "billing_ym": run.billing_ym, "version": run.version},
            row_count=row_count,
        )
    )


def _commit_billing_transition(db: Session, conflict_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BillingConflictError(conflict_message) from exc


def _run_details(db: Session, run_id: int) -> list[BillingRunDetail]:
    return list(
        db.scalars(
            select(BillingRunDetail)
            .where(BillingRunDetail.run_id == run_id, BillingRunDetail.deleted_at.is_(None))
            .order_by(BillingRunDetail.room_id.asc(), BillingRunDetail.id.asc())
        )
    )


def _published_rent_confirm_components(
    db: Session,
    run: BillingRun,
    detail: BillingRunDetail,
) -> dict[str, Any]:
    contract = _active_contract_for_period(db, detail.room_id, run.billing_ym)
    rent_amount = contract.rent if contract is not None else None
    electricity_amount = detail.subtotal
    fixed_fee_amount = _active_fixed_fee_amount(db, detail.room_id)
    exception_amount = _active_exception_amount(db, detail.room_id, run.billing_ym)
    total_amount = sum(
        _amount_or_zero(value)
        for value in (rent_amount, electricity_amount, fixed_fee_amount, exception_amount)
    )

    return {
        "rent_amount": rent_amount,
        "electricity_amount": electricity_amount,
        "fixed_fee_amount": fixed_fee_amount,
        "exception_amount": exception_amount,
        "total_amount": total_amount,
        "amounts": {
            "billing_run_id": run.id,
            "billing_run_detail_id": detail.id,
            "billing_ym": run.billing_ym,
            "run_version": run.version,
            "rent": {
                "amount": rent_amount,
                "tenant_contract_id": contract.id if contract is not None else None,
            },
            "electricity": {"amount": electricity_amount},
            "fixed_fee": {"amount": fixed_fee_amount},
            "exception": {"amount": exception_amount},
            "total": {"amount": total_amount},
        },
    }


def _active_contract_for_period(db: Session, room_id: int, billing_ym: str) -> TenantContract | None:
    period_start, period_end = _billing_month_bounds(billing_ym)
    return db.scalar(
        select(TenantContract)
        .where(
            TenantContract.room_id == room_id,
            TenantContract.deleted_at.is_(None),
            (TenantContract.lease_start_date.is_(None) | (TenantContract.lease_start_date <= period_end)),
            (TenantContract.lease_end_date.is_(None) | (TenantContract.lease_end_date >= period_start)),
        )
        .order_by(TenantContract.lease_start_date.desc().nulls_last(), TenantContract.id.desc())
    )


def _billing_month_bounds(billing_ym: str) -> tuple[date, date]:
    year = int(billing_ym[:4])
    month = int(billing_ym[4:6])
    period_start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return period_start, date.fromordinal(next_month.toordinal() - 1)


def _active_fixed_fee_amount(db: Session, room_id: int) -> int:
    return int(
        db.scalar(
            select(func.sum(RoomFixedFee.amount)).where(
                RoomFixedFee.room_id == room_id,
                RoomFixedFee.deleted_at.is_(None),
            )
        )
        or 0
    )


def _active_exception_amount(db: Session, room_id: int, billing_ym: str) -> int:
    return int(
        db.scalar(
            select(func.sum(ExceptionCharge.amount)).where(
                ExceptionCharge.room_id == room_id,
                ExceptionCharge.billing_ym == billing_ym,
                ExceptionCharge.deleted_at.is_(None),
            )
        )
        or 0
    )


def _amount_or_zero(value: int | None) -> int:
    return value or 0


def _negate_amount(value: int | None) -> int | None:
    return None if value is None else -value


def _calculate_non_split_room(
    db: Session,
    *,
    room: Room,
    billing_ym: str,
    mode: str,
    write_exceptions: bool,
) -> RoomCalculation:
    if mode == "normal":
        return _calculate_normal_room(db, room, billing_ym, write_exceptions)
    if mode == "special_price":
        return _calculate_special_price_room(db, room, billing_ym, write_exceptions)
    if mode == "jingping_merge":
        return _calculate_jingping_merge_room(db, room, billing_ym, write_exceptions)
    if mode == "total_sub":
        return _calculate_total_sub_room(db, room, billing_ym, write_exceptions)
    return _skip(room, mode, f"unsupported billing mode: {room.billing_mode}")


def _calculate_normal_room(
    db: Session,
    room: Room,
    billing_ym: str,
    write_exceptions: bool,
) -> RoomCalculation:
    assignment = _primary_assignment(_active_assignments_for_room(db, room.id, billing_ym))
    if assignment is None:
        return _skip(room, "normal", "missing active meter assignment")
    usage = _usage_for_assignment(db, assignment, billing_ym, None)
    if isinstance(usage, str):
        _record_reading_exception(db, assignment.id, billing_ym, usage, write_exceptions)
        return _skip(room, "normal", usage)
    price = _avg_price(db, assignment.meter_id, billing_ym)
    if price is None:
        return _skip(room, "normal", "missing average price")
    amount = _round_ntd(Decimal(usage.usage) * _decimal(price.price))
    source_ref = {
        "mode": "normal",
        "usage": asdict(usage),
        "avg_price": {"id": price.id, "meter_id": price.meter_id, "price": str(price.price)},
    }
    return _calculated(room, "normal", amount, source_ref)


def _calculate_special_price_room(
    db: Session,
    room: Room,
    billing_ym: str,
    write_exceptions: bool,
) -> RoomCalculation:
    assignment = _primary_assignment(_active_assignments_for_room(db, room.id, billing_ym))
    if assignment is None:
        return _skip(room, "special_price", "missing active meter assignment")
    usage = _usage_for_assignment(db, assignment, billing_ym, None)
    if isinstance(usage, str):
        _record_reading_exception(db, assignment.id, billing_ym, usage, write_exceptions)
        return _skip(room, "special_price", usage)
    price = db.scalar(
        select(SpecialPrice).where(SpecialPrice.room_id == room.id, SpecialPrice.deleted_at.is_(None))
    )
    if price is None:
        return _skip(room, "special_price", "missing special price")
    amount = _round_ntd(Decimal(usage.usage) * _decimal(price.price))
    source_ref = {
        "mode": "special_price",
        "usage": asdict(usage),
        "special_price": {"id": price.id, "room_id": price.room_id, "price": str(price.price)},
    }
    return _calculated(room, "special_price", amount, source_ref)


def _calculate_jingping_merge_room(
    db: Session,
    room: Room,
    billing_ym: str,
    write_exceptions: bool,
) -> RoomCalculation:
    suffix_match = TRAILING_ROOM_NUMBER.search(room.room_code)
    if suffix_match is None:
        return _skip(room, "jingping_merge", "room code does not end with 401, 402, 403, or 404")
    suffix = suffix_match.group(1)
    if suffix in {"402", "404"}:
        return _skip(room, "jingping_merge", "included in paired Jingping bill")
    sibling_suffix = {"401": "402", "403": "404"}.get(suffix)
    if sibling_suffix is None:
        return _skip(room, "jingping_merge", "room is not a Jingping billing parent")
    sibling_code = f"{room.room_code[: suffix_match.start(1)]}{sibling_suffix}"
    sibling = db.scalar(
        select(Room).where(
            Room.site_id == room.site_id,
            Room.room_code == sibling_code,
            Room.deleted_at.is_(None),
        )
    )
    if sibling is None:
        return _skip(room, "jingping_merge", f"missing paired room {sibling_code}")

    primary_assignment = _primary_assignment(_active_assignments_for_room(db, room.id, billing_ym))
    sibling_assignment = _primary_assignment(_active_assignments_for_room(db, sibling.id, billing_ym))
    if primary_assignment is None or sibling_assignment is None:
        return _skip(room, "jingping_merge", "missing active paired meter assignment")

    usages: list[UsageResult] = []
    for assignment in (primary_assignment, sibling_assignment):
        usage = _usage_for_assignment(db, assignment, billing_ym, None)
        if isinstance(usage, str):
            _record_reading_exception(db, assignment.id, billing_ym, usage, write_exceptions)
            return _skip(room, "jingping_merge", usage)
        usages.append(usage)

    price = _avg_price(db, primary_assignment.meter_id, billing_ym)
    if price is None:
        return _skip(room, "jingping_merge", "missing average price")
    merged_usage = sum(usage.usage for usage in usages)
    amount = _round_ntd(Decimal(merged_usage) * _decimal(price.price))
    source_ref = {
        "mode": "jingping_merge",
        "merged_usage": merged_usage,
        "components": [asdict(usage) for usage in usages],
        "avg_price": {"id": price.id, "meter_id": price.meter_id, "price": str(price.price)},
    }
    return _calculated(room, "jingping_merge", amount, source_ref)


def _calculate_total_sub_room(
    db: Session,
    room: Room,
    billing_ym: str,
    write_exceptions: bool,
) -> RoomCalculation:
    assignments = _active_assignments_for_room(db, room.id, billing_ym)
    total_assignment = _assignment_by_category(assignments, TOTAL_ALIASES) or _primary_assignment(assignments)
    sub_assignment = _assignment_by_category(assignments, SUB_ALIASES)
    if total_assignment is None:
        return _skip(room, "total_sub", "missing total meter assignment")

    if sub_assignment is not None and sub_assignment.id != total_assignment.id:
        total_usage = _usage_for_assignment(db, total_assignment, billing_ym, None)
        sub_usage = _usage_for_assignment(db, sub_assignment, billing_ym, None)
    else:
        total_usage = _usage_for_assignment(db, total_assignment, billing_ym, TOTAL_ALIASES)
        sub_usage = _usage_for_assignment(db, total_assignment, billing_ym, SUB_ALIASES)

    if isinstance(total_usage, str):
        _record_reading_exception(db, total_assignment.id, billing_ym, total_usage, write_exceptions)
        return _skip(room, "total_sub", total_usage)
    if isinstance(sub_usage, str):
        exception_assignment_id = sub_assignment.id if sub_assignment is not None else total_assignment.id
        _record_reading_exception(db, exception_assignment_id, billing_ym, sub_usage, write_exceptions)
        return _skip(room, "total_sub", sub_usage)

    net_usage = total_usage.usage - sub_usage.usage
    if net_usage < 0:
        reason = f"negative usage: total usage {total_usage.usage} is below sub usage {sub_usage.usage}"
        _record_reading_exception(db, total_assignment.id, billing_ym, reason, write_exceptions)
        return _skip(room, "total_sub", reason)

    price = _avg_price(db, total_assignment.meter_id, billing_ym)
    if price is None:
        return _skip(room, "total_sub", "missing average price")
    amount = _round_ntd(Decimal(net_usage) * _decimal(price.price))
    source_ref = {
        "mode": "total_sub",
        "total_usage": asdict(total_usage),
        "sub_usage": asdict(sub_usage),
        "net_usage": net_usage,
        "avg_price": {"id": price.id, "meter_id": price.meter_id, "price": str(price.price)},
    }
    return _calculated(room, "total_sub", amount, source_ref)


def _calculate_total_bill_split_room(
    db: Session,
    *,
    room: Room,
    billing_ym: str,
    calculated_by_room: dict[int, RoomCalculation],
) -> RoomCalculation:
    bill_rows = db.scalars(
        select(ExceptionCharge).where(
            ExceptionCharge.room_id == room.id,
            ExceptionCharge.billing_ym == billing_ym,
            ExceptionCharge.deleted_at.is_(None),
        )
    ).all()
    bill_rows = [row for row in bill_rows if _is_taipower_charge_type(row.charge_type)]
    if not bill_rows:
        return _skip(room, "total_bill_split", "missing Taipower bill exception charge")
    bill_total = sum(row.amount for row in bill_rows)

    sibling_rooms = db.scalars(
        select(Room)
        .where(Room.site_id == room.site_id, Room.id != room.id, Room.deleted_at.is_(None))
        .order_by(Room.room_code.asc(), Room.id.asc())
    ).all()
    child_calculations = [
        calculated_by_room[sibling.id]
        for sibling in sibling_rooms
        if _normalize_mode(sibling.billing_mode) == "normal" and sibling.id in calculated_by_room
    ]
    skipped_children = [calculation for calculation in child_calculations if calculation.status != "calculated"]
    if skipped_children:
        skipped_codes = ", ".join(calculation.room_code for calculation in skipped_children)
        return _skip(room, "total_bill_split", f"normal child room skipped: {skipped_codes}")
    child_total = sum(calculation.subtotal or 0 for calculation in child_calculations)
    amount = bill_total - child_total
    source_ref = {
        "mode": "total_bill_split",
        "taipower_bill_total": bill_total,
        "exception_charges": [
            {"id": row.id, "charge_type": row.charge_type, "amount": row.amount} for row in bill_rows
        ],
        "child_rooms": [
            {
                "room_id": calculation.room_id,
                "room_code": calculation.room_code,
                "amount": calculation.subtotal,
            }
            for calculation in child_calculations
        ],
    }
    return _calculated(room, "total_bill_split", amount, source_ref)


def _usage_for_assignment(
    db: Session,
    assignment: RoomMeterAssignment,
    billing_ym: str,
    kind_aliases: set[str] | None,
) -> UsageResult | str:
    current = _reading_for(db, assignment.id, billing_ym, kind_aliases)
    if current is None:
        return "missing current reading"

    if billing_ym == assignment.effective_from_ym:
        if assignment.initial_reading is None:
            return "missing initial reading"
        prior_reading = assignment.initial_reading
        prior_reading_id = None
    else:
        prior = _prior_reading_for(db, assignment.id, billing_ym, kind_aliases)
        if prior is None:
            return "missing prior reading"
        prior_reading = prior.reading
        prior_reading_id = prior.id

    if current.reading < prior_reading:
        return f"negative usage: reading {current.reading} is below prior reading {prior_reading}"
    return UsageResult(
        assignment_id=assignment.id,
        meter_id=assignment.meter_id,
        meter_category=assignment.meter_category,
        reading_kind=current.reading_kind,
        current_reading_id=current.id,
        prior_reading_id=prior_reading_id,
        current_reading=current.reading,
        prior_reading=prior_reading,
        usage=current.reading - prior_reading,
    )


def _reading_for(
    db: Session,
    assignment_id: int,
    billing_ym: str,
    kind_aliases: set[str] | None,
) -> MeterReading | None:
    rows = db.scalars(
        select(MeterReading)
        .where(
            MeterReading.assignment_id == assignment_id,
            MeterReading.billing_ym == billing_ym,
            MeterReading.deleted_at.is_(None),
        )
        .order_by(MeterReading.id.desc())
    ).all()
    if kind_aliases is None:
        return rows[0] if rows else None
    normalized_aliases = {_normalize_token(alias) for alias in kind_aliases}
    for row in rows:
        if _normalize_token(row.reading_kind) in normalized_aliases:
            return row
    return None


def _prior_reading_for(
    db: Session,
    assignment_id: int,
    billing_ym: str,
    kind_aliases: set[str] | None,
) -> MeterReading | None:
    """Most recent reading strictly before billing_ym.

    Handles non-monthly billing (單月/雙月/每月): the prior reading may be
    several months back, not exactly the previous calendar month.
    """
    rows = db.scalars(
        select(MeterReading)
        .where(
            MeterReading.assignment_id == assignment_id,
            MeterReading.billing_ym < billing_ym,
            MeterReading.deleted_at.is_(None),
        )
        .order_by(MeterReading.billing_ym.desc(), MeterReading.id.desc())
    ).all()
    if kind_aliases is None:
        return rows[0] if rows else None
    normalized_aliases = {_normalize_token(alias) for alias in kind_aliases}
    for row in rows:
        if _normalize_token(row.reading_kind) in normalized_aliases:
            return row
    return None


def _record_reading_exception(
    db: Session,
    assignment_id: int,
    billing_ym: str,
    reason: str,
    write_exceptions: bool,
) -> None:
    if not write_exceptions:
        return
    existing = db.scalar(
        select(ReadingException).where(
            ReadingException.assignment_id == assignment_id,
            ReadingException.billing_ym == billing_ym,
            ReadingException.deleted_at.is_(None),
        )
    )
    if existing is not None:
        existing.reason = reason
        return
    db.add(ReadingException(assignment_id=assignment_id, billing_ym=billing_ym, reason=reason))
    db.flush()


def _active_assignments_for_room(db: Session, room_id: int, billing_ym: str) -> list[RoomMeterAssignment]:
    return list(
        db.scalars(
            select(RoomMeterAssignment)
            .where(
                RoomMeterAssignment.room_id == room_id,
                RoomMeterAssignment.effective_from_ym <= billing_ym,
                (RoomMeterAssignment.effective_to_ym.is_(None) | (RoomMeterAssignment.effective_to_ym >= billing_ym)),
                RoomMeterAssignment.deleted_at.is_(None),
            )
            .order_by(RoomMeterAssignment.id.asc())
        )
    )


def _primary_assignment(assignments: list[RoomMeterAssignment]) -> RoomMeterAssignment | None:
    if not assignments:
        return None
    return _assignment_by_category(assignments, MAIN_ALIASES) or assignments[0]


def _assignment_by_category(
    assignments: list[RoomMeterAssignment],
    aliases: set[str],
) -> RoomMeterAssignment | None:
    normalized_aliases = {_normalize_token(alias) for alias in aliases}
    for assignment in assignments:
        if _normalize_token(assignment.meter_category) in normalized_aliases:
            return assignment
    return None


def _avg_price(db: Session, meter_id: int, billing_ym: str) -> AvgPrice | None:
    return db.scalar(
        select(AvgPrice).where(
            AvgPrice.meter_id == meter_id,
            AvgPrice.billing_ym == billing_ym,
            AvgPrice.deleted_at.is_(None),
        )
    )


def _rooms_for_scope(db: Session, scope: dict[str, Any]) -> list[Room]:
    statement = select(Room).where(Room.deleted_at.is_(None))
    if scope.get("type") == "all":
        pass
    elif "site_ids" in scope:
        statement = statement.where(Room.site_id.in_(scope["site_ids"]))
    elif "room_ids" in scope:
        statement = statement.where(Room.id.in_(scope["room_ids"]))
    elif "management_unit" in scope:
        site_ids = select(Site.id).where(
            Site.management_unit == scope["management_unit"],
            Site.deleted_at.is_(None),
        )
        statement = statement.where(Room.site_id.in_(site_ids))
    else:
        raise BillingInputError("unsupported billing scope")
    return list(db.scalars(statement.order_by(Room.site_id.asc(), Room.room_code.asc(), Room.id.asc())))


def _latest_rent_confirm_amounts(db: Session, billing_ym: str) -> dict[int, int]:
    rows = db.scalars(
        select(RentConfirm)
        .where(
            RentConfirm.billing_ym == billing_ym,
            RentConfirm.electricity_amount.is_not(None),
            RentConfirm.deleted_at.is_(None),
        )
        .order_by(RentConfirm.room_id.asc(), RentConfirm.run_version.desc(), RentConfirm.id.desc())
    ).all()
    by_room: dict[int, int] = {}
    for row in rows:
        if row.room_id not in by_room and row.electricity_amount is not None:
            by_room[row.room_id] = row.electricity_amount
    return by_room


def _normalize_mode(value: str | None) -> str:
    token = _normalize_token(value)
    if token in NORMAL_MODES:
        return "normal"
    if token in {_normalize_token(value) for value in SPECIAL_PRICE_MODES}:
        return "special_price"
    if token in {_normalize_token(value) for value in JINGPING_MERGE_MODES}:
        return "jingping_merge"
    if token in {_normalize_token(value) for value in TOTAL_SUB_MODES}:
        return "total_sub"
    if token in {_normalize_token(value) for value in TOTAL_BILL_SPLIT_MODES}:
        return "total_bill_split"
    return token or "normal"


def _normalize_token(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("-", "_")


def _is_taipower_charge_type(value: str) -> bool:
    token = _normalize_token(value)
    return token in {_normalize_token(item) for item in TAIPOWER_CHARGE_TYPES} or "台電" in value


def _usage_from_golden(data: dict[str, Any]) -> int:
    current = int(data["current_reading"])
    prior = int(data.get("prior_reading", data.get("initial_reading")))
    usage = current - prior
    if usage < 0:
        raise BillingInputError("golden case contains negative usage")
    return usage


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _round_ntd(amount: Decimal) -> int:
    # Money rule from the O365 manual: final per-room electricity is rounded
    # to integer NT$ with Decimal ROUND_HALF_UP, after all usage math is done.
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _calculated(room: Room, mode: str, amount: int, source_ref: dict[str, Any]) -> RoomCalculation:
    return RoomCalculation(
        room_id=room.id,
        room_code=room.room_code,
        site_id=room.site_id,
        mode=mode,
        status="calculated",
        subtotal=amount,
        reason=None,
        source_ref=source_ref,
        snapshot={"room_id": room.id, "room_code": room.room_code, "mode": mode, "source_ref": source_ref},
    )


def _skip(room: Room, mode: str, reason: str) -> RoomCalculation:
    return RoomCalculation(
        room_id=room.id,
        room_code=room.room_code,
        site_id=room.site_id,
        mode=mode,
        status="skipped",
        subtotal=None,
        reason=reason,
        source_ref=None,
        snapshot={"room_id": room.id, "room_code": room.room_code, "mode": mode, "reason": reason},
    )


def _try_advisory_xact_lock(db: Session, key: str) -> bool:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    return bool(db.scalar(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}))


def _advisory_xact_lock(db: Session, key: str) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})
