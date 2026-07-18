"""好室資料客服助理——Claude tool-use 迴圈。

流程:使用者提問 → Claude 依語意模型決定呼叫 run_query / aggregate →
以既有引擎執行(繼承權限/scope/稽核)→ Claude 以 present 交付答案,
答案可附 widget 陣列供前端渲染(聊天內嵌圖 or AI 生成儀表板)。
"""
from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.tools import ASSISTANT_TABLES, execute_aggregate, execute_query, execute_revenue
from app.config import settings
from app.db.models import AppUser, AuditLog, ColumnMeta, TableMeta

_client: Anthropic | None = None
_MAX_TURNS = 6

OFFTOPIC_REPLY = (
    "我是好室系統的資料客服助理,只能回答與系統資料相關的問題"
    "(社區、房號、房客、租金、電費、帳單等)。您的問題似乎與系統無關,我無法協助。"
    "您可以試試:「○○社區本月應收總額」「王小姐這個月帳單」。"
)


# USD / 1M tokens(input, output);cache read=0.1×input、cache write=1.25×input
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus": (5.0, 25.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
}

_TOOL_ZH = {"run_query": "查詢", "aggregate": "彙總", "revenue": "金額統計"}
_BY_ZH = {"site": "依社區", "month": "依帳月", "room": "依房號"}
_MEASURE_ZH = {
    "total": "應收總額", "rent": "租金", "electricity": "電費",
    "fixed_fee": "固定費", "exception": "例外費",
}


def _price_of(model: str) -> tuple[float, float]:
    for prefix, price in _PRICING_PER_MTOK.items():
        if model.startswith(prefix):
            return price
    return (5.0, 25.0)


def _cost_usd(totals: dict[str, int], model: str) -> float:
    i, o = _price_of(model)
    usd = (
        totals["input"] * i
        + totals["output"] * o
        + totals["cache_read"] * i * 0.1
        + totals["cache_write"] * i * 1.25
    ) / 1e6
    return round(usd, 4)


def _table_labels(db: Session) -> dict[str, str]:
    rows = db.scalars(select(TableMeta).where(TableMeta.deleted_at.is_(None))).all()
    return {t.code: t.label for t in rows}


def _source_label(tool: str, inputs: dict[str, Any], labels: dict[str, str]) -> str:
    if tool == "revenue":
        parts = [_BY_ZH.get(str(inputs.get("by")), ""), _MEASURE_ZH.get(str(inputs.get("measure", "total")), "")]
        ym = inputs.get("billing_ym")
        if ym:
            parts.append(str(ym))
        detail = "・".join(p for p in parts if p)
        return f"金額統計「租金確認」({detail})" if detail else "金額統計「租金確認」"
    tc = str(inputs.get("table_code", ""))
    zh = labels.get(tc, tc)
    return f"{_TOOL_ZH.get(tool, tool)}「{zh}」"


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 未設定,請在 api/.env 加入金鑰")
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_query",
        "description": (
            "查一張資料表的明細列。filters 每項為 {col, op, val},"
            "op 只能是 eq/contains/in/range/isnull。sort 每項為 {col, dir},dir=asc/desc,"
            "由資料庫排序後才取前 size 筆。用於查個案(某房客、某房號)。"
            "注意:最多回 50 筆、不是全量——要找最大/最小/前N名必須帶 sort 讓資料庫排序,"
            "禁止不帶 sort 拿回傳列自己挑;rent_confirm 的金額排名不要用本工具,用 revenue。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_code": {"type": "string"},
                "filters": {"type": "array", "items": {"type": "object"}},
                "sort": {"type": "array", "items": {"type": "object"}},
                "size": {"type": "integer"},
            },
            "required": ["table_code"],
        },
    },
    {
        "name": "aggregate",
        "description": (
            "彙總。對一張表 group by 一個欄位、對一個數值欄位做 sum/avg/count/max/min。"
            "用於統計與趨勢(各月應收、各狀態筆數)。回傳每列 {group, value}。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_code": {"type": "string"},
                "group_by": {"type": "string"},
                "fn": {"type": "string", "enum": ["sum", "avg", "count", "max", "min"]},
                "measure_col": {"type": "string"},
                "filters": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["table_code", "group_by", "fn"],
        },
    },
    {
        "name": "revenue",
        "description": (
            "rent_confirm 金額統計與金額排名的唯一正確工具——應收/租金/電費/固定費/例外費的"
            "加總(sum)、平均(avg)、最貴/最低/前N名。"
            "它會自動只取每(房號,帳月,收費類型)的最新 run_version(避免重算灌水;"
            "用 aggregate 或 run_query 對 rent_confirm 的金額欄位做統計或排名都會算錯),並可跨表關聯到社區。"
            "by=site 依社區、month 依帳月、room 依房號;measure 選金額欄位;billing_ym 選填(YYYYMM);"
            "order=desc/asc 金額排序方向(by=month 固定依月份)。"
            "排名題用 by=room(或 site)+order=desc(最貴)/asc(最低),結果已排好序,取前 N 筆即可。"
            "回傳每列 {group, value},group 是社區名/房號名,可直接呈現。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "by": {"type": "string", "enum": ["site", "month", "room"]},
                "measure": {
                    "type": "string",
                    "enum": ["total", "rent", "electricity", "fixed_fee", "exception"],
                },
                "fn": {"type": "string", "enum": ["sum", "avg"]},
                "billing_ym": {"type": "string"},
                "order": {"type": "string", "enum": ["desc", "asc"]},
            },
            "required": ["by"],
        },
    },
    {
        "name": "present",
        "description": (
            "交付最終答案給使用者。answer 用繁體中文。"
            "若要呈現圖表或儀表板,填 widgets 陣列(可多個);單純文字回答則省略 widgets。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "widgets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["kpi", "bar", "line", "pie", "stacked-bar", "table"],
                            },
                            "title": {"type": "string"},
                            "label": {"type": "string"},
                            "value": {"type": "number"},
                            "unit": {"type": "string"},
                            "data": {"type": "array", "items": {"type": "object"}},
                            "columns": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "object"}},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["answer"],
        },
    },
]

_RULES = """【作答規則】
1. 只依工具回傳的資料回答。查無資料就明說「查無資料」,絕不臆測或編造數字。
2. 問題與好室系統資料無關(天氣/股票/閒聊/寫作等)→ 不呼叫任何工具,直接用 present 回覆固定訊息:
   「{offtopic}」
3. 系統相關但資料不存在的能力(是否已繳款、房東名下總額)→ 用 present 誠實說明系統沒有這筆資料,不硬湊。
4. 問題模糊(缺月份、社區名不明、多筆同名)→ 先反問使用者,或在答案裡明確講出你採用的假設。
5. 「這個月/最近」等相對時間 → 先用 aggregate 查該表最大的 billing_ym 對齊,不要用今天日期猜。
6. 對 rent_confirm 的任何金額統計或排名(應收/租金/電費/固定費/例外費的總額、平均、
   最貴/最低/前N名)一律用 revenue 工具——它已自動只取每房每月最新 run_version 並可依社區關聯;
   排名用 by=room(或 site)搭配 order=desc(最貴)/asc(最低),結果已排好序,取前 N 筆即可。
   禁止用 aggregate 對 rent_confirm 的金額欄位做 sum/avg(不會去重,必定算錯);
   也禁止用 run_query 撈回來的列自己加總或挑最大最小(最多只回 50 筆、非全量,必定漏算)。
   run_query 只用來看個案明細,要排序務必帶 sort 由資料庫排。
7. 選圖規則:時間趨勢→line;占比/組成→pie;分類比較→bar;單一數字→kpi;明細清單→table。
   使用者要「儀表板」時,用 present 的 widgets 放多個 widget(通常 2 個 kpi + 1~3 張圖)。
8. 使用者要求做圖/圖表/比較時,present 必須附上對應 widget,且把查到的數據完整填入 data 陣列:
   bar/pie 每列 {"group": 名稱, "value": 數值};line 每列 {"x": 時間, "value": 數值}。data 留空會被退回。
9. 需要多筆獨立查詢時(例如比較多個社區),盡量在同一回合一次發出多個工具呼叫(可並行),減少往返時間。
10. answer 必須是純文字(可換行),不要用 markdown 表格/粗體/emoji——表格類內容請放 table widget。
11. 每次答案結尾用一句話交代查了哪張表、什麼條件(前端會顯示為來源)。務必以 present 交付。
12. 回答與 widget 一律呈現名稱(房號、社區名),不得出現資料庫內部代理鍵(room_id、site_id 等數字 id);
    工具回傳只有 id 時,先查 room/site 表把 id 對應成名稱再呈現。"""


def build_system_prompt(db: Session, user: AppUser) -> str:
    lines = [
        "你是好室包租代管系統的資料客服助理。只能用工具查資料庫回答,不可捏造。",
        "可查的資料表與欄位(code「標籤」: 欄位(標籤,型別)):",
    ]
    tables = db.scalars(
        select(TableMeta).where(TableMeta.code.in_(ASSISTANT_TABLES), TableMeta.deleted_at.is_(None))
    ).all()
    for t in tables:
        cols = db.scalars(
            select(ColumnMeta).where(
                ColumnMeta.table_code == t.code, ColumnMeta.deleted_at.is_(None)
            )
        ).all()
        cs = ", ".join(f"{c.col_code}({c.label},{c.type})" for c in cols)
        lines.append(f"- {t.code}「{t.label}」: {cs}")
    lines += [
        "關聯: room.site_id→site;rent_confirm/tenant_contract/room_fixed_fee/exception_charge 的 room_id→room;"
        "avg_price.meter_id→meter。",
        "同義詞: 案場=社區=site;房號=房=room;房客=租約=tenant_contract;帳單=應收=rent_confirm。",
        "billing_ym 是 YYYYMM 六碼字串。",
        _RULES.replace("{offtopic}", OFFTOPIC_REPLY),
    ]
    return "\n".join(lines)


def ask(db: Session, user: AppUser, question: str, context: str | None = None) -> dict[str, Any]:
    client = _get_client()
    system = build_system_prompt(db, user)
    content = (
        f"(使用者目前正在系統的「{context}」頁面提問,回答時可參考此情境)\n{question}"
        if context
        else question
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    sources: list[dict[str, Any]] = []
    labels = _table_labels(db)
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    def usage_summary() -> dict[str, Any]:
        return {
            "cost_usd": _cost_usd(totals, settings.assistant_model),
            "input_tokens": totals["input"] + totals["cache_read"] + totals["cache_write"],
            "output_tokens": totals["output"],
            "model": settings.assistant_model,
        }

    for _ in range(_MAX_TURNS):
        resp = client.messages.create(
            model=settings.assistant_model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.assistant_effort},
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )

        u = resp.usage
        totals["input"] += u.input_tokens or 0
        totals["output"] += u.output_tokens or 0
        totals["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        totals["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0

        if resp.stop_reason != "tool_use":
            text = next((b.text for b in resp.content if b.type == "text"), "")
            return {"answer": text or OFFTOPIC_REPLY, "widgets": [], "sources": sources, "usage": usage_summary()}

        messages.append({"role": "assistant", "content": resp.content})
        results: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "present":
                widgets = block.input.get("widgets") or []
                empty = [
                    w.get("title") or w.get("type", "?")
                    for w in widgets
                    if w.get("type") in {"bar", "line", "pie", "stacked-bar"} and not (w.get("data") or [])
                ]
                if empty:
                    # 圖表沒帶數據 → 退回叫模型把查到的數字填進 data 再交付(自癒)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"present 被拒絕:圖表 {empty} 的 data 是空的。"
                            "請把剛才查到的實際數據填入該 widget 的 data 陣列"
                            "(每列 {\"group\": 名稱, \"value\": 數值};折線圖用 x 代替 group)後重新 present。"
                        ),
                        "is_error": True,
                    })
                    continue
                _audit(db, user, question, sources)
                return {
                    "answer": block.input.get("answer", ""),
                    "widgets": widgets,
                    "sources": sources,
                    "usage": usage_summary(),
                }
            try:
                if block.name == "run_query":
                    data = execute_query(db, user, **block.input)
                elif block.name == "aggregate":
                    data = execute_aggregate(db, user, **block.input)
                elif block.name == "revenue":
                    data = execute_revenue(db, user, **block.input)
                else:
                    raise ValueError(f"未知工具:{block.name}")
                sources.append({
                    "tool": block.name,
                    "label": _source_label(block.name, block.input, labels),
                    **block.input,
                })
                content, is_error = json.dumps(data, ensure_ascii=False, default=str), False
            except Exception as exc:  # noqa: BLE001 — 回饋給模型讓它換方式
                content, is_error = f"錯誤:{exc}", True
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})

    return {"answer": "查詢過於複雜,請縮小範圍再問一次。", "widgets": [], "sources": sources, "usage": usage_summary()}


def _audit(db: Session, user: AppUser, question: str, sources: list[dict[str, Any]]) -> None:
    db.add(
        AuditLog(
            actor=user.id,
            action="assistant_ask",
            filters={"question": question, "sources": sources},
        )
    )
    db.commit()
