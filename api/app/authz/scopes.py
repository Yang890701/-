from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import false, select
from sqlalchemy.orm import Session, object_session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

from app.db.models import (
    AppUser,
    AvgPrice,
    ExceptionCharge,
    Meter,
    MeterReading,
    MgmtReminder,
    RentConfirm,
    Room,
    RoomFixedFee,
    RoomMeterAssignment,
    Site,
    TenantContract,
    UserScope,
)

PredicateFactory = Callable[[list[int]], ColumnElement[bool]]


@dataclass(frozen=True)
class SiteLinkage:
    model: type
    path: str
    predicate: PredicateFactory | None


def _direct_site_id(site_ids: list[int]) -> ColumnElement[bool]:
    return Site.id.in_(site_ids)


def _room_site_id(site_ids: list[int]) -> ColumnElement[bool]:
    return Room.site_id.in_(site_ids)


def _via_room_id(model: type) -> PredicateFactory:
    def predicate(site_ids: list[int]) -> ColumnElement[bool]:
        room_ids = select(Room.id).where(Room.deleted_at.is_(None), Room.site_id.in_(site_ids))
        return model.room_id.in_(room_ids)

    return predicate


def _via_assignment(site_ids: list[int]) -> ColumnElement[bool]:
    assignment_ids = (
        select(RoomMeterAssignment.id)
        .join(Room, Room.id == RoomMeterAssignment.room_id)
        .where(
            RoomMeterAssignment.deleted_at.is_(None),
            Room.deleted_at.is_(None),
            Room.site_id.in_(site_ids),
        )
    )
    return MeterReading.assignment_id.in_(assignment_ids)


def _nullable_mgmt_site_id(site_ids: list[int]) -> ColumnElement[bool]:
    return MgmtReminder.site_id.in_(site_ids)


# Site-agnostic tables intentionally have no site path. Scoped non-admin users
# receive a false predicate for them rather than broad access.
SITE_LINKAGE_REGISTRY: dict[str, SiteLinkage] = {
    "site": SiteLinkage(Site, "site.id", _direct_site_id),
    "room": SiteLinkage(Room, "room.site_id", _room_site_id),
    "tenant_contract": SiteLinkage(
        TenantContract, "tenant_contract.room_id -> room.site_id", _via_room_id(TenantContract)
    ),
    "rent_confirm": SiteLinkage(
        RentConfirm, "rent_confirm.room_id -> room.site_id", _via_room_id(RentConfirm)
    ),
    "room_fixed_fee": SiteLinkage(
        RoomFixedFee, "room_fixed_fee.room_id -> room.site_id", _via_room_id(RoomFixedFee)
    ),
    "exception_charge": SiteLinkage(
        ExceptionCharge, "exception_charge.room_id -> room.site_id", _via_room_id(ExceptionCharge)
    ),
    "meter_reading": SiteLinkage(
        MeterReading,
        "meter_reading.assignment_id -> room_meter_assignment.room_id -> room.site_id",
        _via_assignment,
    ),
    "mgmt_reminder": SiteLinkage(MgmtReminder, "mgmt_reminder.site_id (nullable)", _nullable_mgmt_site_id),
    "meter": SiteLinkage(Meter, "site-agnostic: scoped non-admin safe deny", None),
    "avg_price": SiteLinkage(AvgPrice, "site-agnostic: scoped non-admin safe deny", None),
}


def _scope_session(user: AppUser) -> Session:
    session = object_session(user)
    if session is None:
        raise ValueError("scope_predicate requires an ORM-attached AppUser")
    return session


def _site_scope_ids(db: Session, user: AppUser) -> tuple[bool, list[int]]:
    scopes = db.scalars(
        select(UserScope).where(UserScope.user_id == user.id, UserScope.deleted_at.is_(None))
    ).all()
    if any(scope.scope_type == "all" for scope in scopes):
        return True, []

    site_ids: list[int] = []
    for scope in scopes:
        if scope.scope_type != "site" or scope.scope_value is None:
            continue
        try:
            site_ids.append(int(scope.scope_value))
        except ValueError:
            continue
    return False, sorted(set(site_ids))


def scope_predicate(user: AppUser, table_code: str) -> ColumnElement[bool] | None:
    if user.role in {"admin", "manager"}:
        return None

    db = _scope_session(user)
    has_all_scope, site_ids = _site_scope_ids(db, user)
    if has_all_scope:
        return None

    linkage = SITE_LINKAGE_REGISTRY.get(table_code)
    if linkage is None or linkage.predicate is None or not site_ids:
        return false()
    return linkage.predicate(site_ids)


def apply_scope(statement: Select, user: AppUser, table_code: str) -> Select:
    predicate = scope_predicate(user, table_code)
    if predicate is None:
        return statement
    return statement.where(predicate)
