from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    pass


class CoreColumns:
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LineageColumns:
    legacy_key: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str | None] = mapped_column(Text)


def active_where():
    return text("deleted_at IS NULL")


class EnumManagementType(CoreColumns, LineageColumns, Base):
    __tablename__ = "enum_management_type"
    __table_args__ = (
        Index("uq_enum_management_type_code_active", "code", unique=True, postgresql_where=active_where()),
        {"comment": "管理類型"},
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class EnumFeeItem(CoreColumns, LineageColumns, Base):
    __tablename__ = "enum_fee_item"
    __table_args__ = (
        Index("uq_enum_fee_item_code_active", "code", unique=True, postgresql_where=active_where()),
        {"comment": "費用項目"},
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class EnumMeterCategory(CoreColumns, LineageColumns, Base):
    __tablename__ = "enum_meter_category"
    __table_args__ = (
        Index("uq_enum_meter_category_code_active", "code", unique=True, postgresql_where=active_where()),
        {"comment": "電表類別"},
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class EnumPayType(CoreColumns, LineageColumns, Base):
    __tablename__ = "enum_pay_type"
    __table_args__ = (
        Index("uq_enum_pay_type_code_active", "code", unique=True, postgresql_where=active_where()),
        {"comment": "付款類型"},
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class EnumMap(CoreColumns, Base):
    __tablename__ = "enum_map"
    __table_args__ = (
        Index(
            "uq_enum_map_domain_raw_active",
            "domain",
            "raw_value",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "匯入列舉對照"},
    )

    domain: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_value: Mapped[str] = mapped_column(Text, nullable=False)


class Site(CoreColumns, LineageColumns, Base):
    __tablename__ = "site"
    __table_args__ = (
        Index("uq_site_code_active", "site_code", unique=True, postgresql_where=active_where()),
        {"comment": "案場"},
    )

    site_code: Mapped[str] = mapped_column(Text, nullable=False, comment="案場")
    name: Mapped[str | None] = mapped_column(Text, comment="案場顯示名稱")
    address: Mapped[str | None] = mapped_column(Text, comment="地址")
    management_unit: Mapped[str | None] = mapped_column(Text, comment="管理單位")


class Meter(CoreColumns, LineageColumns, Base):
    __tablename__ = "meter"
    __table_args__ = (
        Index(
            "uq_meter_electricity_code_active",
            "electricity_code",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "電號"},
    )

    electricity_code: Mapped[str] = mapped_column(Text, nullable=False, comment="電號")
    name: Mapped[str | None] = mapped_column(Text, comment="電表名稱")
    management_type_id: Mapped[int | None] = mapped_column(ForeignKey("enum_management_type.id"))
    management_type: Mapped[str | None] = mapped_column(Text, comment="管理類型來源文字")
    note: Mapped[str | None] = mapped_column(Text)


class Room(CoreColumns, LineageColumns, Base):
    __tablename__ = "room"
    __table_args__ = (
        Index("uq_room_code_active", "room_code", unique=True, postgresql_where=active_where()),
        Index(
            "uq_room_site_code_active", "site_id", "room_code", unique=True, postgresql_where=active_where()
        ),
        {"comment": "房號"},
    )

    site_id: Mapped[int] = mapped_column(ForeignKey("site.id"), nullable=False)
    room_code: Mapped[str] = mapped_column(Text, nullable=False, comment="房號")
    room_name: Mapped[str | None] = mapped_column(Text, comment="房號名稱")
    meter_id: Mapped[int | None] = mapped_column(ForeignKey("meter.id"))
    management_type_id: Mapped[int | None] = mapped_column(ForeignKey("enum_management_type.id"))
    management_type: Mapped[str | None] = mapped_column(Text, comment="管理類型來源文字")
    management_contact: Mapped[str | None] = mapped_column(Text, comment="管理窗口")
    billing_mode: Mapped[str | None] = mapped_column(Text, comment="電費計費方式")


class RoomMeterAssignment(CoreColumns, LineageColumns, Base):
    __tablename__ = "room_meter_assignment"
    __table_args__ = (
        CheckConstraint("effective_from_ym ~ '^[0-9]{6}$'", name="ck_rma_effective_from_ym"),
        CheckConstraint(
            "effective_to_ym IS NULL OR effective_to_ym ~ '^[0-9]{6}$'", name="ck_rma_effective_to_ym"
        ),
        Index(
            "uq_room_meter_assignment_nk_active",
            "room_id",
            "meter_category",
            "effective_from_ym",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "房號電表指派"},
    )

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meter.id"), nullable=False)
    effective_from_ym: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    effective_to_ym: Mapped[str | None] = mapped_column(CHAR(6))
    initial_reading: Mapped[int | None] = mapped_column(Integer)
    final_reading: Mapped[int | None] = mapped_column(Integer)
    meter_category_id: Mapped[int | None] = mapped_column(ForeignKey("enum_meter_category.id"))
    meter_category: Mapped[str] = mapped_column(Text, nullable=False, comment="電表類別")


class MeterReading(CoreColumns, LineageColumns, Base):
    __tablename__ = "meter_reading"
    __table_args__ = (
        CheckConstraint("billing_ym ~ '^[0-9]{6}$'", name="ck_meter_reading_billing_ym"),
        Index(
            "uq_meter_reading_assignment_ym_kind_active",
            "assignment_id",
            "billing_ym",
            "reading_kind",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "抄表讀數"},
    )

    assignment_id: Mapped[int] = mapped_column(ForeignKey("room_meter_assignment.id"), nullable=False)
    billing_ym: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    reading_kind: Mapped[str] = mapped_column(Text, nullable=False)
    reading: Mapped[int] = mapped_column(Integer, nullable=False)
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachment.id"))


class MeterEvent(CoreColumns, LineageColumns, Base):
    __tablename__ = "meter_event"
    __table_args__ = (
        CheckConstraint("event_ym ~ '^[0-9]{6}$'", name="ck_meter_event_event_ym"),
        {"comment": "電表事件"},
    )

    assignment_id: Mapped[int] = mapped_column(ForeignKey("room_meter_assignment.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_ym: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    old_reading: Mapped[int | None] = mapped_column(Integer)
    new_reading: Mapped[int | None] = mapped_column(Integer)


class ReadingException(CoreColumns, LineageColumns, Base):
    __tablename__ = "reading_exception"
    __table_args__ = (
        CheckConstraint("billing_ym ~ '^[0-9]{6}$'", name="ck_reading_exception_billing_ym"),
        Index(
            "uq_reading_exception_assignment_ym_active",
            "assignment_id",
            "billing_ym",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "抄表例外"},
    )

    assignment_id: Mapped[int] = mapped_column(ForeignKey("room_meter_assignment.id"), nullable=False)
    billing_ym: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))


class AvgPrice(CoreColumns, LineageColumns, Base):
    __tablename__ = "avg_price"
    __table_args__ = (
        CheckConstraint("billing_ym ~ '^[0-9]{6}$'", name="ck_avg_price_billing_ym"),
        Index(
            "uq_avg_price_meter_ym_active",
            "meter_id",
            "billing_ym",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "平均電價"},
    )

    meter_id: Mapped[int] = mapped_column(ForeignKey("meter.id"), nullable=False)
    billing_ym: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachment.id"))


class SpecialPrice(CoreColumns, LineageColumns, Base):
    __tablename__ = "special_price"
    __table_args__ = (
        Index("uq_special_price_room_active", "room_id", unique=True, postgresql_where=active_where()),
        {"comment": "特殊電價"},
    )

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    meter_category_id: Mapped[int | None] = mapped_column(ForeignKey("enum_meter_category.id"))
    meter_category: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


class RoomFixedFee(CoreColumns, LineageColumns, Base):
    __tablename__ = "room_fixed_fee"
    __table_args__ = (
        Index(
            "uq_room_fixed_fee_room_item_active",
            "room_id",
            "fee_item_id",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "房號固定費用"},
    )

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    fee_item_id: Mapped[int] = mapped_column(ForeignKey("enum_fee_item.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)


class ExceptionCharge(CoreColumns, LineageColumns, Base):
    __tablename__ = "exception_charge"
    __table_args__ = (
        CheckConstraint(
            "billing_ym IS NULL OR billing_ym ~ '^[0-9]{6}$'", name="ck_exception_charge_billing_ym"
        ),
        {"comment": "例外收費"},
    )

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    billing_ym: Mapped[str | None] = mapped_column(CHAR(6))
    charge_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class RentConfirm(CoreColumns, LineageColumns, Base):
    __tablename__ = "rent_confirm"
    __table_args__ = (
        CheckConstraint("billing_ym IS NULL OR billing_ym ~ '^[0-9]{6}$'", name="ck_rent_confirm_billing_ym"),
        Index(
            "uq_rent_confirm_room_ym_type_version_active",
            "room_id",
            "billing_ym",
            "charge_type",
            "run_version",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "租金確認"},
    )

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    billing_ym: Mapped[str | None] = mapped_column(CHAR(6))
    charge_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rent_amount: Mapped[int | None] = mapped_column(Integer)
    electricity_amount: Mapped[int | None] = mapped_column(Integer)
    fixed_fee_amount: Mapped[int | None] = mapped_column(Integer)
    exception_amount: Mapped[int | None] = mapped_column(Integer)
    total_amount: Mapped[int | None] = mapped_column(Integer)
    amounts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class TenantContract(CoreColumns, LineageColumns, Base):
    __tablename__ = "tenant_contract"
    __table_args__ = (
        Index(
            "uq_tenant_contract_room_start_active",
            "room_id",
            "lease_start_date",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "租客合約"},
    )

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    lease_start_date: Mapped[date | None] = mapped_column(Date)
    lease_end_date: Mapped[date | None] = mapped_column(Date)
    rent: Mapped[int | None] = mapped_column(Integer)
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    line_contact_id: Mapped[int | None] = mapped_column(ForeignKey("line_contact.id"))
    pay_type_id: Mapped[int | None] = mapped_column(ForeignKey("enum_pay_type.id"))


class LineContact(CoreColumns, LineageColumns, Base):
    __tablename__ = "line_contact"
    __table_args__ = (
        Index("uq_line_contact_line_id_active", "line_id", unique=True, postgresql_where=active_where()),
        {"comment": "Line 聯絡人"},
    )

    line_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MgmtReminder(CoreColumns, LineageColumns, Base):
    __tablename__ = "mgmt_reminder"
    __table_args__ = ({"comment": "管理提醒"},)

    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("site.id"))
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class BillingRun(CoreColumns, Base):
    __tablename__ = "billing_run"
    __table_args__ = (
        CheckConstraint("billing_ym ~ '^[0-9]{6}$'", name="ck_billing_run_billing_ym"),
        CheckConstraint(
            "status IN ('draft','calculated','approved','published','reversed')",
            name="ck_billing_run_status",
        ),
        Index(
            "uq_billing_run_ym_version_active",
            "billing_ym",
            "version",
            unique=True,
            postgresql_where=active_where(),
        ),
        Index("uq_billing_run_idempotency_key", "idempotency_key", unique=True),
        {"comment": "計費批次"},
    )

    billing_ym: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class BillingRunDetail(CoreColumns, Base):
    __tablename__ = "billing_run_detail"
    __table_args__ = (
        Index(
            "uq_billing_run_detail_run_room_active",
            "run_id",
            "room_id",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "計費批次房號明細"},
    )

    run_id: Mapped[int] = mapped_column(ForeignKey("billing_run.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    subtotal: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(Text)


class BillingRunChargeLine(CoreColumns, Base):
    __tablename__ = "billing_run_charge_line"
    __table_args__ = ({"comment": "計費批次收費項目"},)

    detail_id: Mapped[int] = mapped_column(ForeignKey("billing_run_detail.id"), nullable=False)
    charge_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class GoldenCase(CoreColumns, Base):
    __tablename__ = "golden_case"
    __table_args__ = (
        Index("uq_golden_case_code_active", "case_code", unique=True, postgresql_where=active_where()),
        {"comment": "計費黃金案例"},
    )

    case_code: Mapped[str] = mapped_column(Text, nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class AppUser(CoreColumns, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        Index("uq_app_user_username_active", "username", unique=True, postgresql_where=active_where()),
        {"comment": "系統使用者"},
    )

    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshSession(CoreColumns, Base):
    __tablename__ = "refresh_session"
    __table_args__ = (
        Index("uq_refresh_session_token_hash", "token_hash", unique=True),
        {"comment": "Refresh token sessions"},
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)


class UserScope(CoreColumns, Base):
    __tablename__ = "user_scope"
    __table_args__ = (
        CheckConstraint("scope_type IN ('all','site','mgmt_unit')", name="ck_user_scope_type"),
        Index(
            "uq_user_scope_user_scope_active",
            "user_id",
            "scope_type",
            "scope_value",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "使用者資料範圍"},
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_value: Mapped[str | None] = mapped_column(Text)


class TableMeta(CoreColumns, Base):
    __tablename__ = "table_meta"
    __table_args__ = (
        Index("uq_table_meta_code_active", "code", unique=True, postgresql_where=active_where()),
        {"comment": "資料表中繼資料"},
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    physical_table: Mapped[str] = mapped_column(Text, nullable=False)
    read_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )


class ColumnMeta(CoreColumns, Base):
    __tablename__ = "column_meta"
    __table_args__ = (
        Index(
            "uq_column_meta_table_col_active",
            "table_code",
            "col_code",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "欄位中繼資料"},
    )

    table_code: Mapped[str] = mapped_column(Text, nullable=False)
    col_code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    physical_column: Mapped[str] = mapped_column(Text, nullable=False)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    operators: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    read_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    write_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    filter_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    sort_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    export_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )


class MetadataChangeLog(CoreColumns, Base):
    __tablename__ = "metadata_change_log"
    __table_args__ = ({"comment": "Metadata change governance log"},)

    actor: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    requires_second_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'applied'"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(CoreColumns, Base):
    __tablename__ = "audit_log"
    __table_args__ = ({"comment": "稽核紀錄"},)

    actor: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    table_code: Mapped[str | None] = mapped_column(Text)
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    row_count: Mapped[int | None] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Attachment(CoreColumns, Base):
    __tablename__ = "attachment"
    __table_args__ = (
        Index("uq_attachment_object_key_active", "object_key", unique=True, postgresql_where=active_where()),
        {"comment": "附件"},
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class Job(CoreColumns, Base):
    __tablename__ = "job"
    __table_args__ = ({"comment": "背景工作"},)

    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortalLinkGroup(CoreColumns, Base):
    __tablename__ = "portal_link_group"
    __table_args__ = (
        Index("uq_portal_link_group_code_active", "group_code", unique=True, postgresql_where=active_where()),
        {"comment": "入口首頁-連結群組"},
    )

    group_code: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class PortalLinkCategory(CoreColumns, Base):
    __tablename__ = "portal_link_category"
    __table_args__ = (
        Index("uq_portal_link_category_code_active", "category_code", unique=True, postgresql_where=active_where()),
        {"comment": "入口首頁-連結分類"},
    )

    category_code: Mapped[str] = mapped_column(Text, nullable=False)
    group_code: Mapped[str] = mapped_column(Text, nullable=False)
    category_name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class PortalLink(CoreColumns, Base):
    __tablename__ = "portal_link"
    __table_args__ = ({"comment": "入口首頁-連結"},)

    category_code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class PortalNotice(CoreColumns, Base):
    __tablename__ = "portal_notice"
    __table_args__ = ({"comment": "入口首頁-公告"},)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ImportBatch(CoreColumns, Base):
    __tablename__ = "import_batch"
    __table_args__ = ({"comment": "匯入批次"},)

    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    checksums: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRowError(CoreColumns, Base):
    __tablename__ = "import_row_error"
    __table_args__ = ({"comment": "匯入列錯誤"},)

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id"), nullable=False)
    source_row: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class LegacyKeyMap(CoreColumns, Base):
    __tablename__ = "legacy_key_map"
    __table_args__ = (
        Index(
            "uq_legacy_key_map_domain_key_active",
            "domain",
            "legacy_key",
            unique=True,
            postgresql_where=active_where(),
        ),
        {"comment": "舊系統鍵值對照"},
    )

    domain: Mapped[str] = mapped_column(Text, nullable=False)
    legacy_key: Mapped[str] = mapped_column(Text, nullable=False)
    new_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RawStagingTable(CoreColumns):
    @declared_attr.directive
    def __table_args__(cls):
        return {"comment": cls.__doc__}

    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))
    source_key: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class StgSite(RawStagingTable, Base):
    """案場原始匯入"""

    __tablename__ = "stg_site"


class StgMeter(RawStagingTable, Base):
    """電號原始匯入"""

    __tablename__ = "stg_meter"


class StgRoom(RawStagingTable, Base):
    """房號原始匯入"""

    __tablename__ = "stg_room"


class StgMeterReading(RawStagingTable, Base):
    """抄表原始匯入"""

    __tablename__ = "stg_meter_reading"


class StgAvgPrice(RawStagingTable, Base):
    """平均電價原始匯入"""

    __tablename__ = "stg_avg_price"


class StgLineContact(RawStagingTable, Base):
    """Line 聯絡人原始匯入"""

    __tablename__ = "stg_line_contact"


class StgSpecialPrice(RawStagingTable, Base):
    """特殊電價原始匯入"""

    __tablename__ = "stg_special_price"


class StgRoomFixedFee(RawStagingTable, Base):
    """固定費用原始匯入"""

    __tablename__ = "stg_room_fixed_fee"


class StgExceptionCharge(RawStagingTable, Base):
    """例外收費原始匯入"""

    __tablename__ = "stg_exception_charge"


class StgRentConfirm(RawStagingTable, Base):
    """租金確認原始匯入"""

    __tablename__ = "stg_rent_confirm"


class StgTenantContract(RawStagingTable, Base):
    """租約原始匯入"""

    __tablename__ = "stg_tenant_contract"


class StgTenantMonthly(RawStagingTable, Base):
    """每月租約原始匯入"""

    __tablename__ = "stg_tenant_monthly"


class StgMgmtReminder(RawStagingTable, Base):
    """管理提醒原始匯入"""

    __tablename__ = "stg_mgmt_reminder"
