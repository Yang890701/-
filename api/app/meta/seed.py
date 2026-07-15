from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ColumnMeta, TableMeta
from app.db.session import SessionLocal

ALL_ROLES = ["admin", "manager", "accounting", "staff", "readonly"]
SENSITIVE_ROLES = ["admin", "manager", "accounting"]
WRITE_ROLES = ["admin", "manager"]

OPERATORS_BY_TYPE = {
    "text": ["eq", "contains", "isnull"],
    "enum": ["eq", "in"],
    "date": ["eq", "range"],
    "ym": ["eq", "range"],
    "number": ["eq", "range"],
}


@dataclass(frozen=True)
class ColumnSeed:
    code: str
    physical: str
    label: str
    type: str
    filterable: bool = True
    sensitive: bool = False


@dataclass(frozen=True)
class TableSeed:
    code: str
    physical: str
    label: str
    columns: list[ColumnSeed]


TABLES = [
    TableSeed(
        "site",
        "site",
        "社區",
        [
            ColumnSeed("site_code", "site_code", "社區代碼", "text"),
            ColumnSeed("name", "name", "社區名稱", "text"),
            ColumnSeed("address", "address", "地址", "text"),
            ColumnSeed("management_unit", "management_unit", "管理單位", "text"),
        ],
    ),
    TableSeed(
        "meter",
        "meter",
        "電表",
        [
            ColumnSeed("electricity_code", "electricity_code", "電號", "text"),
            ColumnSeed("name", "name", "電表名稱", "text"),
            ColumnSeed("management_type", "management_type", "管理型態", "enum"),
            ColumnSeed("note", "note", "備註", "text"),
        ],
    ),
    TableSeed(
        "room",
        "room",
        "房間",
        [
            ColumnSeed("site_id", "site_id", "社區ID", "number"),
            ColumnSeed("room_code", "room_code", "房號", "text"),
            ColumnSeed("room_name", "room_name", "房間名稱", "text"),
            ColumnSeed("meter_id", "meter_id", "電表ID", "number"),
            ColumnSeed("management_type", "management_type", "管理型態", "enum"),
            ColumnSeed("management_contact", "management_contact", "管理窗口", "text"),
            ColumnSeed("billing_mode", "billing_mode", "計費模式", "enum"),
        ],
    ),
    TableSeed(
        "tenant_contract",
        "tenant_contract",
        "租客合約",
        [
            ColumnSeed("room_id", "room_id", "房間ID", "number"),
            ColumnSeed("lease_start_date", "lease_start_date", "起租日", "date"),
            ColumnSeed("lease_end_date", "lease_end_date", "退租日", "date"),
            ColumnSeed("rent", "rent", "租金", "number", sensitive=True),
            ColumnSeed("contact_name", "contact_name", "租客姓名", "text"),
            ColumnSeed("contact_phone", "contact_phone", "租客電話", "text", sensitive=True),
            ColumnSeed("line_contact_id", "line_contact_id", "Line聯絡ID", "number"),
            ColumnSeed("pay_type_id", "pay_type_id", "繳費方式ID", "number"),
        ],
    ),
    TableSeed(
        "rent_confirm",
        "rent_confirm",
        "租金確認",
        [
            ColumnSeed("room_id", "room_id", "房間ID", "number"),
            ColumnSeed("billing_ym", "billing_ym", "帳務年月", "ym"),
            ColumnSeed("charge_type", "charge_type", "收費類型", "enum"),
            ColumnSeed("run_version", "run_version", "計費版本", "number"),
            ColumnSeed("status", "status", "狀態", "enum"),
            ColumnSeed("rent_amount", "rent_amount", "租金金額", "number", sensitive=True),
            ColumnSeed("electricity_amount", "electricity_amount", "電費金額", "number", sensitive=True),
            ColumnSeed("fixed_fee_amount", "fixed_fee_amount", "固定費金額", "number", sensitive=True),
            ColumnSeed("exception_amount", "exception_amount", "例外費用金額", "number", sensitive=True),
            ColumnSeed("total_amount", "total_amount", "繳費總額", "number", sensitive=True),
        ],
    ),
    TableSeed(
        "meter_reading",
        "meter_reading",
        "抄表讀數",
        [
            ColumnSeed("assignment_id", "assignment_id", "房間電表關聯ID", "number"),
            ColumnSeed("billing_ym", "billing_ym", "帳務年月", "ym"),
            ColumnSeed("reading_kind", "reading_kind", "讀數種類", "enum"),
            ColumnSeed("reading", "reading", "讀數", "number"),
            ColumnSeed("attachment_id", "attachment_id", "附件ID", "number"),
        ],
    ),
    TableSeed(
        "avg_price",
        "avg_price",
        "平均電價",
        [
            ColumnSeed("meter_id", "meter_id", "電表ID", "number"),
            ColumnSeed("billing_ym", "billing_ym", "帳務年月", "ym"),
            ColumnSeed("price", "price", "平均單價", "number"),
            ColumnSeed("attachment_id", "attachment_id", "附件ID", "number"),
        ],
    ),
    TableSeed(
        "room_fixed_fee",
        "room_fixed_fee",
        "房間固定費",
        [
            ColumnSeed("room_id", "room_id", "房間ID", "number"),
            ColumnSeed("fee_item_id", "fee_item_id", "費用項目ID", "number"),
            ColumnSeed("amount", "amount", "固定費金額", "number", sensitive=True),
        ],
    ),
    TableSeed(
        "exception_charge",
        "exception_charge",
        "例外收費",
        [
            ColumnSeed("room_id", "room_id", "房間ID", "number"),
            ColumnSeed("billing_ym", "billing_ym", "帳務年月", "ym"),
            ColumnSeed("charge_type", "charge_type", "收費類型", "enum"),
            ColumnSeed("amount", "amount", "例外費用金額", "number", sensitive=True),
            ColumnSeed("note", "note", "備註", "text"),
        ],
    ),
    TableSeed(
        "mgmt_reminder",
        "mgmt_reminder",
        "管理提醒",
        [
            ColumnSeed("target_type", "target_type", "提醒對象類型", "enum"),
            ColumnSeed("target_id", "target_id", "提醒對象ID", "number"),
            ColumnSeed("site_id", "site_id", "社區ID", "number"),
            ColumnSeed("due_date", "due_date", "提醒日期", "date"),
            ColumnSeed("status", "status", "狀態", "enum"),
            ColumnSeed("created_by", "created_by", "建立者ID", "number"),
        ],
    ),
]


def _column_values(table: TableSeed, column: ColumnSeed) -> dict:
    roles = SENSITIVE_ROLES if column.sensitive else ALL_ROLES
    operators = OPERATORS_BY_TYPE[column.type] if column.filterable else []
    return {
        "table_code": table.code,
        "col_code": column.code,
        "label": column.label,
        "type": column.type,
        "physical_column": column.physical,
        "filterable": column.filterable,
        "operators": operators,
        "read_roles": roles,
        "write_roles": WRITE_ROLES,
        "filter_roles": roles if column.filterable else [],
        "sort_roles": roles,
        "export_roles": roles,
    }


def seed_metadata(db: Session, actor: str | None = None) -> dict[str, int]:
    del actor  # Reserved for future governed non-seed metadata edits.
    counts = {"tables_inserted": 0, "tables_updated": 0, "columns_inserted": 0, "columns_updated": 0}

    for table in TABLES:
        existing_table = db.scalar(
            select(TableMeta).where(TableMeta.code == table.code, TableMeta.deleted_at.is_(None))
        )
        if existing_table is None:
            db.add(
                TableMeta(
                    code=table.code,
                    label=table.label,
                    physical_table=table.physical,
                    read_roles=ALL_ROLES,
                )
            )
            counts["tables_inserted"] += 1
        else:
            existing_table.label = table.label
            existing_table.physical_table = table.physical
            existing_table.read_roles = ALL_ROLES
            counts["tables_updated"] += 1

        for column in table.columns:
            values = _column_values(table, column)
            existing_column = db.scalar(
                select(ColumnMeta).where(
                    ColumnMeta.table_code == table.code,
                    ColumnMeta.col_code == column.code,
                    ColumnMeta.deleted_at.is_(None),
                )
            )
            if existing_column is None:
                db.add(ColumnMeta(**values))
                counts["columns_inserted"] += 1
            else:
                for key, value in values.items():
                    setattr(existing_column, key, value)
                counts["columns_updated"] += 1

    db.commit()
    return counts


def main() -> None:
    with SessionLocal() as db:
        counts = seed_metadata(db, actor="seed")
    print(counts)


if __name__ == "__main__":
    main()
