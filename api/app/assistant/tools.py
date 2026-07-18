"""好室資料客服助理——工具執行層。

設計原則:AI 不自己寫 SQL,只能透過這裡的函式呼叫「既有的查詢引擎」
(app.routers.data 的管線),因此自動繼承角色欄位遮罩、列級 user_scope
與稽核。demo 以 admin 使用者跑,權限不擋;正式版換成真使用者即自動生效。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.fields import allowed_columns
from app.db.models import AppUser, Base, Meter, RentConfirm, Room, Site
from app.routers.data import (
    FilterItem,
    SortItem,
    _apply_active,
    _apply_query_pipeline,
    _apply_scope,
    _apply_sort,
    _base_statement,
    _build_context,
    _filter_expression,
    _metadata_for_table,
)
from app.services.billing import (
    MONTHLY_RENT_CONFIRM_CHARGE_TYPE,
    REVERSAL_RENT_CONFIRM_CHARGE_TYPE,
)

# 助理可存取的資料表(demo 範圍;其餘表未註冊 → 碰不到)
ASSISTANT_TABLES: list[str] = [
    "site",
    "room",
    "tenant_contract",
    "rent_confirm",
    "meter_reading",
    "avg_price",
    "room_fixed_fee",
    "exception_charge",
    "mgmt_reminder",
]

_AGG_FNS = {"sum": func.sum, "avg": func.avg, "count": func.count, "max": func.max, "min": func.min}
_MAX_ROWS = 50


def execute_query(
    db: Session,
    user: AppUser,
    table_code: str,
    filters: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    size: int = 20,
) -> list[dict[str, Any]]:
    """查單一資料表的明細列——完全沿用 /api/data/query 的權限與 scope 管線。"""
    if table_code not in ASSISTANT_TABLES:
        raise ValueError(f"不可查詢的資料表:{table_code}")
    fi = [FilterItem(**f) for f in (filters or [])]
    si = [SortItem(**s) for s in (sort or [])]
    plan, table, columns_by_code = _build_context(db, table_code, user, fi, si)
    statement = _apply_query_pipeline(_base_statement(table, plan), table, plan, fi, user)
    statement = _apply_sort(statement, table, columns_by_code, si).limit(min(int(size or 20), _MAX_ROWS))
    return [dict(row) for row in db.execute(statement).mappings().all()]


def execute_aggregate(
    db: Session,
    user: AppUser,
    table_code: str,
    group_by: str,
    fn: str,
    measure_col: str | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """彙總:對一張表 group by 一個欄位,對數值欄位做 sum/avg/count/max/min。

    僅允許使用者角色可讀的欄位;沿用 active(未刪除)與列級 scope。
    回傳每列 {group, value}。
    """
    if table_code not in ASSISTANT_TABLES:
        raise ValueError(f"不可查詢的資料表:{table_code}")
    if fn not in _AGG_FNS:
        raise ValueError("fn 只能是 sum/avg/count/max/min")
    # 鐵則防呆:rent_confirm 金額統計必須經 run_version 去重,aggregate 做不到,
    # 只靠 prompt 約束不可靠——程式層直接擋,錯誤訊息會引導模型改用 revenue。
    if table_code == "rent_confirm" and fn in {"sum", "avg"} and measure_col in _RENT_CONFIRM_MONEY_COLS:
        raise ValueError("rent_confirm 的金額統計禁止用 aggregate(不會做 run_version 去重,必定算錯),請改用 revenue 工具")

    table_meta, columns = _metadata_for_table(db, table_code, user)  # 無讀取權限會擋下
    by_code = {c.col_code: c for c in columns}
    allowed = allowed_columns(user.role, table_code, db)

    if group_by not in allowed or group_by not in by_code:
        raise ValueError(f"不可用的分組欄位:{group_by}")
    physical = Base.metadata.tables.get(table_meta.physical_table)
    if physical is None:
        raise ValueError("資料表未註冊")

    group_col = physical.c[by_code[group_by].physical_column]
    if fn == "count":
        measure = func.count().label("value")
    else:
        if not measure_col or measure_col not in allowed or measure_col not in by_code:
            raise ValueError(f"不可用的量測欄位:{measure_col}")
        measure = _AGG_FNS[fn](physical.c[by_code[measure_col].physical_column]).label("value")

    statement = select(group_col.label("group"), measure).select_from(physical)
    statement = _apply_active(statement, physical)
    for item in filters or []:
        col = by_code.get(item.get("col"))
        if col is None:
            raise ValueError(f"不可用的篩選欄位:{item.get('col')}")
        statement = statement.where(
            _filter_expression(physical.c[col.physical_column], item.get("op"), item.get("val"))
        )
    statement = _apply_scope(statement, user, table_code)
    statement = statement.group_by(group_col).order_by(measure.desc()).limit(_MAX_ROWS)
    return [dict(row) for row in db.execute(statement).mappings().all()]


# lookup 對照支援的實體:kind → (model, 代碼欄, 名稱欄)
_LOOKUP_KINDS = {
    "room": (Room, Room.room_code, Room.room_name),
    "site": (Site, Site.site_code, Site.name),
    "meter": (Meter, Meter.electricity_code, Meter.name),
}


def execute_lookup(
    db: Session,
    user: AppUser,
    kind: str,
    ids: list[int] | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """內部 id ↔ 名稱對照(跨表橋)。

    column_meta 刻意不暴露代理鍵 id,模型因此無法自行把 room_id/site_id
    對回名稱、也拿不到 id 來下篩選——本工具補上這座橋:
    ids=[...] 正查名稱;q='關鍵字' 以代碼/名稱模糊反查 id(最多 20 筆)。
    room 另回 site_id 方便續查。沿用表級 read_roles 與列級 scope。
    """
    if kind not in _LOOKUP_KINDS:
        raise ValueError("kind 只能是 room / site / meter")
    _metadata_for_table(db, kind, user)  # 表級 read_roles 檢查
    model, code_col, name_col = _LOOKUP_KINDS[kind]
    extra = [Room.site_id] if kind == "room" else []
    stmt = select(model.id, code_col.label("code"), name_col.label("name"), *extra).where(
        model.deleted_at.is_(None)
    )
    if ids:
        stmt = stmt.where(model.id.in_([int(i) for i in ids][:100]))
    elif q and str(q).strip():
        pattern = f"%{str(q).strip()}%"
        stmt = stmt.where(code_col.ilike(pattern) | name_col.ilike(pattern))
    else:
        raise ValueError("lookup 需要 ids 或 q 其中之一")
    stmt = _apply_scope(stmt, user, kind).order_by(model.id).limit(100 if ids else 20)
    return [dict(row) for row in db.execute(stmt).mappings().all()]


_REVENUE_MEASURES = {
    "total": RentConfirm.total_amount,
    "rent": RentConfirm.rent_amount,
    "electricity": RentConfirm.electricity_amount,
    "fixed_fee": RentConfirm.fixed_fee_amount,
    "exception": RentConfirm.exception_amount,
}

_RENT_CONFIRM_MONEY_COLS = {
    "rent_amount", "electricity_amount", "fixed_fee_amount", "exception_amount", "total_amount",
}


def execute_revenue(
    db: Session,
    user: AppUser,
    billing_ym: str | None = None,
    by: str = "site",
    measure: str = "total",
    fn: str = "sum",
    order: str = "desc",
) -> list[dict[str, Any]]:
    """正確的『rent_confirm 金額統計/排名』——應收/租金/電費/固定費/例外費的加總或平均。

    rent_confirm 同一(房號, 帳月, 收費類型)可能有多個 run_version(重算),
    本函式只取每組最新版再統計,避免重複計算灌水(直接對全表 SUM/AVG 會算錯)。
    沖銷列(charge_type=沖銷,金額為負)不獨立去重——只在它抵銷的版本仍是
    月結現行最新版時入帳;重開新版後,舊版與其沖銷一併淘汰(否則會少算)。
    無帳月(billing_ym 為空)的列一律排除(匯入殘留,不屬任何月度統計;
    資料速覽會揭露其筆數與合計)。
    by ∈ site（依社區）/ month（依帳月）/ room（依房號）;
    measure ∈ total/rent/electricity/fixed_fee/exception;fn ∈ sum/avg;
    order ∈ desc/asc(金額排序方向,最貴 desc/最低 asc;by=month 固定依月份序)。
    billing_ym 選填(YYYYMM)。回傳每列 {group, value}。
    已套表級 read_roles 與列級 user_scope(demo admin 為 no-op),
    正式版換 get_current_user 即自動生效。
    """
    if by not in {"site", "month", "room"}:
        raise ValueError("by 只能是 site / month / room")
    if measure not in _REVENUE_MEASURES:
        raise ValueError("measure 只能是 total/rent/electricity/fixed_fee/exception")
    if fn not in {"sum", "avg"}:
        raise ValueError("fn 只能是 sum / avg")
    if order not in {"desc", "asc"}:
        raise ValueError("order 只能是 desc / asc")
    _metadata_for_table(db, "rent_confirm", user)  # 表級 read_roles 檢查

    base = [RentConfirm.deleted_at.is_(None), RentConfirm.billing_ym.is_not(None)]
    if billing_ym:
        base.append(RentConfirm.billing_ym == billing_ym)

    # 最新版本表:排除沖銷列——沖銷是「月結某版」的抵銷,若讓它自成 (room, ym, 沖銷)
    # 一組去重,重開新版後過期的負值仍會入帳,沖銷重開月份會整版少算。
    latest = _apply_scope(
        select(
            RentConfirm.room_id,
            RentConfirm.billing_ym,
            RentConfirm.charge_type,
            func.max(RentConfirm.run_version).label("mv"),
        )
        .where(*base, RentConfirm.charge_type != REVERSAL_RENT_CONFIRM_CHARGE_TYPE)
        .group_by(RentConfirm.room_id, RentConfirm.billing_ym, RentConfirm.charge_type),
        user,
        "rent_confirm",
    ).subquery()
    is_reversal = RentConfirm.charge_type == REVERSAL_RENT_CONFIRM_CHARGE_TYPE
    on = (
        (RentConfirm.room_id == latest.c.room_id)
        & (RentConfirm.billing_ym == latest.c.billing_ym)
        & (RentConfirm.run_version == latest.c.mv)
        & (
            # 一般列:對上自己 (room, ym, charge_type) 組的最新版
            (~is_reversal & (RentConfirm.charge_type == latest.c.charge_type))
            # 沖銷列:只在其版本==月結組現行最新版時入帳(未重開=歸零;已重開=淘汰)
            | (is_reversal & (latest.c.charge_type == MONTHLY_RENT_CONFIRM_CHARGE_TYPE))
        )
    )
    col = _REVENUE_MEASURES[measure]
    agg = func.sum(col) if fn == "sum" else func.round(func.avg(col), 2)
    value = agg.label("value")
    ordering = value.desc().nulls_last() if order == "desc" else value.asc().nulls_last()

    if by == "month":
        stmt = (
            select(RentConfirm.billing_ym.label("group"), value)
            .select_from(RentConfirm).join(latest, on).where(*base)
            .group_by(RentConfirm.billing_ym).order_by(RentConfirm.billing_ym)
        )
    elif by == "room":
        stmt = (
            select(Room.room_code.label("group"), value)
            .select_from(RentConfirm).join(latest, on)
            .join(Room, Room.id == RentConfirm.room_id)
            .where(*base, Room.deleted_at.is_(None))
            .group_by(Room.room_code).order_by(ordering, Room.room_code)  # 同額並列時以名稱定序,結果可重現
        )
    else:  # site
        stmt = (
            select(Site.name.label("group"), value)
            .select_from(RentConfirm).join(latest, on)
            .join(Room, Room.id == RentConfirm.room_id)
            .join(Site, Site.id == Room.site_id)
            .where(*base, Room.deleted_at.is_(None), Site.deleted_at.is_(None))
            .group_by(Site.name).order_by(ordering, Site.name)
        )
    stmt = _apply_scope(stmt, user, "rent_confirm")  # 列級 scope(demo admin 為 no-op)
    return [dict(row) for row in db.execute(stmt.limit(_MAX_ROWS)).mappings().all()]
