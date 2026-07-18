"""黃金問題集回歸——把「人工拿 SQL 對 AI 答案」制度化,改 prompt/工具/模型後必跑。

用法(後端 8010 須在跑,DB 用 api/.env 的 DATABASE_URL):
  cd api
  .venv\\Scripts\\python.exe scripts\\golden_qa.py
  .venv\\Scripts\\python.exe scripts\\golden_qa.py --base http://localhost:8010 --only top5

設計:
- 每個 case = 問 AI 一次 + 跑標準答案 SQL 一次,依 check 規則比對。
- 比對是「數值多重集」層級(tie-aware):同額並列時第 N 名是誰不定,
  驗數值不驗名字順序;文字類驗關鍵詞。
- 新增 case:往 CASES 加一筆即可。exit code 0=全過、1=有 fail(可掛 CI)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text as sql_text  # noqa: E402

from app.config import settings  # noqa: E402

# 「取最新 run_version」標準去重子查詢(領域鐵則,所有金額 SQL 都要包這層)
LATEST = (
    "(SELECT DISTINCT ON (room_id, billing_ym, charge_type) * FROM rent_confirm"
    " WHERE deleted_at IS NULL{extra} ORDER BY room_id, billing_ym, charge_type, run_version DESC)"
)


def latest(where: str = "") -> str:
    return LATEST.format(extra=f" AND {where}" if where else "")


_L_202603 = latest("billing_ym='202603'")
_L_202607 = latest("billing_ym='202607'")
_L_ALL = latest()

CASES: list[dict[str, Any]] = [
    {
        "id": "top5-rent-202603",
        "question": "幫我列出今年三月最貴的五筆租金",
        "sql": f"SELECT rc.rent_amount FROM {_L_202603} rc ORDER BY rc.rent_amount DESC NULLS LAST LIMIT 5",
        "check": "values_in_output",
    },
    {
        "id": "cheapest5-rent-202603",
        "question": "今年三月最便宜的五筆租金是哪些?",
        "sql": f"SELECT rc.rent_amount FROM {_L_202603} rc ORDER BY rc.rent_amount ASC NULLS LAST LIMIT 5",
        "check": "values_in_output",
    },
    {
        "id": "total-202607",
        "question": "202607 的應收總額是多少?",
        "sql": f"SELECT SUM(rc.total_amount) FROM {_L_202607} rc",
        "check": "values_in_output",
    },
    {
        "id": "avg-elec-monthly",
        "question": "列出 2026 年每個月的平均電費",
        "sql": f"SELECT ROUND(AVG(rc.electricity_amount), 2) FROM {_L_ALL} rc "
               "WHERE rc.billing_ym LIKE '2026%' GROUP BY rc.billing_ym ORDER BY rc.billing_ym",
        "check": "values_in_output",
        "tolerance": 0.5,  # 模型可能取到小數 1 位呈現
    },
    {
        "id": "no-data-202503",
        "question": "2025年3月的應收總額是多少?",
        "check": "answer_contains_any",
        "expect_any": ["查無", "沒有", "無資料", "不存在", "並無", "無 2025", "無該"],
    },
    {
        "id": "offtopic-weather",
        "question": "今天天氣如何?",
        "check": "answer_contains_any",
        "expect_any": ["只能回答與系統資料相關"],
        "expect_no_tools": True,
    },
]


def ask(base: str, question: str) -> tuple[dict[str, Any], float]:
    req = urllib.request.Request(
        f"{base}/api/assistant/ask",
        data=json.dumps({"question": question}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data, time.perf_counter() - t0


def numbers_in_output(resp: dict[str, Any]) -> Counter:
    """收集 answer 文字 + 所有 widget 裡出現的數值(四捨五入到 2 位)。"""
    found: list[float] = []
    for m in re.findall(r"-?\d[\d,]*(?:\.\d+)?", resp.get("answer", "")):
        try:
            found.append(round(float(m.replace(",", "")), 2))
        except ValueError:
            pass
    for w in resp.get("widgets") or []:
        if isinstance(w.get("value"), (int, float)):
            found.append(round(float(w["value"]), 2))
        for row in (w.get("data") or []) + (w.get("rows") or []):
            for v in (row or {}).values():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    found.append(round(float(v), 2))
    return Counter(found)


def check_case(case: dict[str, Any], resp: dict[str, Any], engine) -> tuple[bool, str]:
    if case["check"] == "values_in_output":
        with engine.connect() as conn:
            expected = [round(float(r[0]), 2) for r in conn.execute(sql_text(case["sql"])) if r[0] is not None]
        actual = numbers_in_output(resp)
        tol = float(case.get("tolerance", 0.01))
        missing: list[float] = []
        pool = list(actual.elements())
        for e in Counter(expected).elements():
            hit = next((a for a in pool if abs(a - e) <= tol), None)
            if hit is None:
                missing.append(e)
            else:
                pool.remove(hit)
        return (not missing, f"缺少數值 {missing}(SQL 期望 {expected})" if missing else f"{len(expected)} 個數值全中")
    if case["check"] == "answer_contains_any":
        answer = resp.get("answer", "")
        hit = next((kw for kw in case["expect_any"] if kw in answer), None)
        if case.get("expect_no_tools") and resp.get("sources"):
            return False, f"不該呼叫工具卻呼叫了:{[s.get('label') for s in resp['sources']]}"
        return (hit is not None, f"命中「{hit}」" if hit else f"answer 未含任一關鍵詞 {case['expect_any']}:{answer[:80]}")
    return False, f"未知 check 類型:{case['check']}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8010")
    parser.add_argument("--only", default=None, help="只跑 id 含此字串的 case")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    cases = [c for c in CASES if not args.only or args.only in c["id"]]
    failures = 0
    total_cost = 0.0
    print(f"黃金問題集:{len(cases)} 題 → {args.base}\n")
    for case in cases:
        try:
            resp, elapsed = ask(args.base, case["question"])
            ok, detail = check_case(case, resp, engine)
            cost = float((resp.get("usage") or {}).get("cost_usd") or 0)
            total_cost += cost
        except Exception as exc:  # noqa: BLE001 — 回歸腳本要跑完全部再總結
            ok, detail, elapsed, cost = False, f"執行失敗:{exc}", 0.0, 0.0
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']:24s} {elapsed:5.1f}s ${cost:.4f}  {detail}")
    print(f"\n{len(cases) - failures}/{len(cases)} 過,共 ${total_cost:.4f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
