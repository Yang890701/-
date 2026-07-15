# HANDOFF — 換機／到公司接續指南

> 最後更新 2026-07-15。**先讀 `log.md`（流水帳＝目前進度與續接點）與 `03-tasks.md`（任務狀態）。**

## 現況（一句話）
好室包租代管系統重寫，**M 層 DMO 已完成並驗證**（登入分權 + 通用檢視/篩選/匯出 xlsx + 審計，真實資料已可匯入）。**下一步從 G 層 T15 開始**（主檔 CRUD → 電費引擎 → 繳租確認 → 一次切換 → 部署）。憲法（`02-constitution.md`）已凍結，G 層動工不需重跑關卡。

## 技術棧
- 前端 `web/`：Next.js 15 + TS + TanStack Table + SheetJS
- 後端 `api/`：FastAPI + SQLAlchemy 2 + Alembic，Python 3.12/3.13 venv（本機用 3.14 亦可）
- DB：PostgreSQL 17

## 新機器建置步驟
```bash
# 1. clone
git clone https://github.com/Yang890701/-.git haoshi && cd haoshi

# 2. PostgreSQL（擇一）：本機裝原生 PG，或用 infra/docker-compose.yml（機器 A 建議）
#    建 dev 資料庫與角色：
#    CREATE ROLE haoshi LOGIN PASSWORD '<自訂>'; CREATE DATABASE haoshi_dev OWNER haoshi;

# 3. 後端
cd api
python -m venv .venv && .venv/Scripts/activate   # Windows；mac/linux: source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://haoshi:<密碼>@localhost:5432/haoshi_dev"
export JWT_SIGNING_KEYS='{"k1":"<換成強金鑰>"}'  JWT_ACTIVE_KID=k1
alembic upgrade head                # 建 schema(48 表)
python -m app.meta.seed             # 灌元數據(表/欄/角色)
python -m app.auth.create_user --username admin --password <自訂> --role admin
python -m app.importer.cli          # 匯入 4 份 Excel（見下方「資料怎麼帶」）
uvicorn app.main:app --port 8000

# 4. 前端
cd ../web && npm install
# NEXT_PUBLIC_API_BASE 預設 http://localhost:8000
npm run dev        # 或 npm run build && npm start
# 開 http://localhost:3000
```

## 資料怎麼帶（重要）
- **4 份來源 Excel 與 O365 PDF 不在 repo**（含房客個資，已由 `.gitignore` 排除）。到公司請**另以隨身碟/安全管道**把這 4 個檔放回專案根目錄，再跑 `python -m app.importer.cli`：
  - `房客資料表.xlsx`、`歷程房客資料表.xlsx`、`管理提醒專區.xlsx`、`繳租表單紀錄檔.xlsx`
- 或者：在原機器 `pg_dump haoshi_dev` 出一份，到公司 `pg_restore`（連清洗後的資料一起帶）。
- 資料模型完整分析在原機器的 `.devline/reference/data-analysis.md`（也含個資樣本、未進 repo），需要可另外帶。

## 開發帳密與安全 TODO（上線前必改）
- dev 種子帳號：`admin` / `admin123`（請改）。
- 本機 PG 超級使用者是 winget 預設 `postgres`（請改）。
- `JWT_SIGNING_KEYS` 目前用 dev 佔位字串，cookie `secure=False`——正式環境務必換強金鑰、開 HTTPS+secure cookie（在部署 T22 處理）。

## 驗收怎麼跑
```bash
cd api && python -m unittest discover -s tests   # 應 29 passed
ruff check .                                       # 應 All checks passed
cd ../web && npm run build && npm run lint         # 應綠
```

## 接續點
讀 `log.md` 最後幾行。下一張任務 = `03-tasks.md` 的 **T15（主檔 CRUD）**；電費引擎 T17 標 `opus`（難、要對帳），實作以 Codex 為主、額度盡切 Claude。景平 401-404 合併電表的度數目前留在 `import_row_error`（標 deferred-to-T16），T16 處理。
