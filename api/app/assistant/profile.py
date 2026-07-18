"""資料速覽(data profile)——把資料庫的「形狀」固化成一段文字注入 system prompt。

目的:模型回答前就知道資料涵蓋哪些月份、各表幾筆、枚舉欄位有哪些值、
社區名單長怎樣,不必浪費工具回合探索,也不會猜錯月份。
成本:掛在 prompt cache 後面,快取命中時近乎免費;本身有 10 分鐘 TTL
in-process 快取,不會每題打一輪 DB。
"""
from __future__ import annotations

import time

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AvgPrice,
    ExceptionCharge,
    MeterReading,
    MgmtReminder,
    RentConfirm,
    Room,
    RoomFixedFee,
    Site,
    TenantContract,
)

_TTL_SECONDS = 600.0
_cache: dict[str, object] = {"text": None, "at": 0.0}


def _count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.deleted_at.is_(None))) or 0


def _distinct_vals(db: Session, col, limit: int = 20) -> list[str]:
    rows = db.scalars(select(distinct(col)).where(col.is_not(None)).order_by(col).limit(limit)).all()
    return [str(r) for r in rows]


def _ym_range(db: Session, model) -> str:
    lo, hi = db.execute(
        select(func.min(model.billing_ym), func.max(model.billing_ym)).where(model.deleted_at.is_(None))
    ).one()
    return f"{lo}–{hi}" if lo else "無資料"


def build_data_profile(db: Session) -> str:
    now = time.monotonic()
    if _cache["text"] and now - float(_cache["at"]) < _TTL_SECONDS:
        return str(_cache["text"])

    months = _distinct_vals(db, RentConfirm.billing_ym, limit=60)
    latest_ym = months[-1] if months else "無"
    charge_types = _distinct_vals(db, RentConfirm.charge_type)
    statuses = _distinct_vals(db, RentConfirm.status)
    null_ym_count, null_ym_total = db.execute(
        select(func.count(), func.coalesce(func.sum(RentConfirm.total_amount), 0)).where(
            RentConfirm.deleted_at.is_(None), RentConfirm.billing_ym.is_(None)
        )
    ).one()
    site_names = db.scalars(
        select(Site.name).where(Site.deleted_at.is_(None), Site.name.is_not(None)).order_by(Site.name)
    ).all()

    counts = {
        "site": _count(db, Site),
        "room": _count(db, Room),
        "tenant_contract": _count(db, TenantContract),
        "rent_confirm": _count(db, RentConfirm),
        "meter_reading": _count(db, MeterReading),
        "avg_price": _count(db, AvgPrice),
        "room_fixed_fee": _count(db, RoomFixedFee),
        "exception_charge": _count(db, ExceptionCharge),
        "mgmt_reminder": _count(db, MgmtReminder),
    }

    lines = [
        "【資料速覽(即時統計,以此為準,不必用工具探索資料範圍)】",
        f"- 資料最新月份:{latest_ym}。「這個月/最近」={latest_ym};「今年」={latest_ym[:4] if latest_ym != '無' else '?'}。",
        f"- rent_confirm「租金確認」:{counts['rent_confirm']} 筆;涵蓋月份:{'、'.join(months) if months else '無'};"
        f"charge_type 值:{'、'.join(charge_types) or '無'};status 值:{'、'.join(statuses) or '無'}。",
        f"- site「案場/社區」:{counts['site']} 個;room「房號」:{counts['room']} 間;"
        f"tenant_contract「租客合約」:{counts['tenant_contract']} 筆。",
        f"- meter_reading「抄表」:{counts['meter_reading']} 筆({_ym_range(db, MeterReading)});"
        f"avg_price「電價」:{counts['avg_price']} 筆({_ym_range(db, AvgPrice)});"
        f"room_fixed_fee:{counts['room_fixed_fee']};exception_charge:{counts['exception_charge']};"
        f"mgmt_reminder:{counts['mgmt_reminder']}。",
        f"- 社區名單(使用者寫近似名時對映到最接近的一個,如「伍華」→「五華」):{'、'.join(str(s) for s in site_names)}。",
    ]
    if null_ym_count:
        lines.insert(3, (
            f"- 注意:另有 {null_ym_count} 筆無帳月(billing_ym 空白)的 rent_confirm(合計 {int(null_ym_total):,} 元),"
            "屬匯入殘留,不納入任何金額統計;使用者問全部總額時可主動註明此排除。"
        ))
    text = "\n".join(lines)
    _cache.update(text=text, at=now)
    return text
