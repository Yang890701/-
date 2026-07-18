"""資料客服助理路由。

- POST /api/assistant/ask       AI 問答(可回傳 widget 陣列)
- GET  /api/assistant/dashboard 固定儀表板(不呼叫 AI,直接跑彙總)

demo 一律以 admin 使用者執行,權限不擋;正式版把 _demo_user 換成
Depends(get_current_user) 即自動繼承 RBAC 與列級 scope。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.assistant.service import ask
from app.assistant.tools import execute_revenue
from app.db.models import AppUser, RentConfirm, Room, Site
from app.db.session import get_db

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class HistoryMsg(BaseModel):
    role: str  # "user" | "assistant"(service 端會再驗證)
    content: str = Field(max_length=4000)


class AskRequest(BaseModel):
    # 長度上限=成本上限:question 直接進 LLM,無上限會被拿來灌 token(financial DoS)
    question: str = Field(max_length=1000)
    context: str | None = Field(default=None, max_length=100)  # 使用者目前所在頁面(Genie 面板帶入)
    history: list[HistoryMsg] | None = Field(default=None, max_length=24)  # 最近幾輪問答,支援「那二月呢」式追問


def _demo_user(db: Session) -> AppUser:
    """DEMO: 以 admin 執行,權限不擋 demo。
    PRODUCTION: 改成 Depends(get_current_user) 即收工。"""
    user = db.scalar(
        select(AppUser).where(AppUser.role == "admin", AppUser.deleted_at.is_(None)).order_by(AppUser.id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="找不到 admin 使用者")
    return user


@router.post("/ask")
def ask_endpoint(payload: AskRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not payload.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="問題不可為空")
    history = [m.model_dump() for m in payload.history or []]
    return ask(db, _demo_user(db), payload.question, context=payload.context, history=history)


@router.get("/dashboard")
def dashboard_endpoint(db: Session = Depends(get_db)) -> dict[str, Any]:
    """固定經營總覽:最新月份應收 KPI + 近 6 月趨勢 + 各社區應收。

    全部走 execute_revenue(已處理 run_version 重算),與 AI 同一套正確邏輯,
    確保儀表板與問答的數字一致。
    """
    user = _demo_user(db)
    by_month = [r for r in execute_revenue(db, user, by="month") if r["group"]]
    if not by_month:
        return {"title": "經營總覽", "widgets": [], "note": "尚無帳務資料"}

    latest_ym = str(by_month[-1]["group"])
    total = float(by_month[-1]["value"] or 0)
    prev = float(by_month[-2]["value"]) if len(by_month) >= 2 and by_month[-2]["value"] else None
    delta = round((total - prev) / prev * 100, 1) if prev else None

    room_count = db.scalar(
        select(func.count(distinct(RentConfirm.room_id))).where(
            RentConfirm.deleted_at.is_(None), RentConfirm.billing_ym == latest_ym
        )
    ) or 0

    avg_elec_rows = execute_revenue(db, user, billing_ym=latest_ym, by="month", measure="electricity", fn="avg")
    avg_elec = float(avg_elec_rows[0]["value"]) if avg_elec_rows and avg_elec_rows[0]["value"] else 0

    total_rooms = db.scalar(select(func.count()).select_from(Room).where(Room.deleted_at.is_(None))) or 0
    avg_per_room = total / room_count if room_count else 0

    composition = []
    for label, measure in [("租金", "rent"), ("電費", "electricity"), ("固定費", "fixed_fee"), ("例外費", "exception")]:
        rows = execute_revenue(db, user, billing_ym=latest_ym, by="month", measure=measure, fn="sum")
        value = float(rows[0]["value"]) if rows and rows[0]["value"] else 0
        if value > 0:
            composition.append({"name": label, "value": int(value)})

    by_site = execute_revenue(db, user, billing_ym=latest_ym, by="site")

    elec_trend = [
        r for r in execute_revenue(db, user, by="month", measure="electricity", fn="avg") if r["group"]
    ]

    rooms_by_site = db.execute(
        select(Site.name.label("group"), func.count(Room.id).label("value"))
        .join(Room, Room.site_id == Site.id)
        .where(Site.deleted_at.is_(None), Room.deleted_at.is_(None))
        .group_by(Site.name)
        .order_by(func.count(Room.id).desc())
    ).mappings().all()

    kpi_total: dict[str, Any] = {
        "type": "kpi", "label": f"{latest_ym} 應收總額", "value": int(total), "unit": "元",
    }
    if delta is not None:
        kpi_total["delta"] = delta

    widgets: list[dict[str, Any]] = [
        kpi_total,
        {"type": "kpi", "label": "本月開帳房數", "value": int(room_count), "unit": f"房 / 共{total_rooms}房"},
        {"type": "kpi", "label": "平均每房應收", "value": int(round(avg_per_room)), "unit": "元/房"},
        {"type": "kpi", "label": "本月平均電費", "value": round(avg_elec, 1), "unit": "元/房"},
        {
            "type": "line",
            "title": "各月應收趨勢",
            "data": [{"x": str(r["group"]), "value": int(r["value"] or 0)} for r in by_month[-6:]],
        },
        {
            "type": "line",
            "title": "各月平均電費趨勢",
            "data": [{"x": str(r["group"]), "value": float(r["value"] or 0)} for r in elec_trend[-6:]],
        },
        {"type": "pie", "title": f"{latest_ym} 收費組成", "data": composition},
        {
            "type": "bar",
            "title": f"{latest_ym} 各社區應收",
            "data": [{"group": r["group"] or "(未命名)", "value": int(r["value"] or 0)} for r in by_site],
        },
        {
            "type": "bar",
            "title": "各社區房號數",
            "data": [{"group": r["group"] or "(未命名)", "value": int(r["value"] or 0)} for r in rooms_by_site],
        },
    ]
    return {"title": f"{latest_ym} 經營總覽", "widgets": widgets}
