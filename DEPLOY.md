# DEPLOY — 免費方案 Demo 部署手冊（給合作對象看用）

> 目標：把好室系統部署到**免費雲**給合作對象看。
> 架構：前端 **Vercel**（Next.js）＋ 後端 **Render**（FastAPI）＋ 資料庫 **Neon**（PostgreSQL）。
> 資料：使用者已決定用**真實資料**。因此：repo 私有、登入才可見、換掉預設帳密、加安全標頭。
>
> ⚠️ 這是 demo 部署，與正式切換（T20/T21）和正式付費檔次（精省/標準）分開，那些仍未動。

---

## 0. 前置（帳號）

| 服務 | 用途 | 免費限制 |
|---|---|---|
| GitHub | 程式碼來源（**已有** 私有 repo `Yang890701/-`，gh 已登入） | — |
| [Neon](https://neon.tech) | PostgreSQL | 免費專案；容量上限，demo 足夠 |
| [Render](https://render.com) | 後端 FastAPI web service | 閒置 ~15 分鐘休眠，冷啟 ~30 秒；磁碟為暫存（附件上傳不持久） |
| [Vercel](https://vercel.com) | 前端 Next.js | 適合 Next；`NEXT_PUBLIC_*` 於 build 期注入 |

本機工具（皆已具備）：`git` / `gh`、免安裝 PG 於 `C:\Users\larry0701\haoshi\pgsql\bin`（pg_dump/pg_restore/psql v17）、`api\.venv`。

---

## 1. 產生正式密鑰（勿進版控）

後端在 `JWT_SIGNING_KEYS` 未設時會**拒絕啟動**。產生一組強金鑰：

```powershell
# 產生一個 kid 與一把 secret（貼到 Render 環境變數，不要寫進 repo）
$kid = "k1"
$secret = & "C:\Users\larry0701\haoshi\repo\api\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"
"JWT_ACTIVE_KID = $kid"
"JWT_SIGNING_KEYS = {""$kid"": ""$secret""}"
```

`JWT_SIGNING_KEYS` 格式必須是 JSON 物件：`{"k1":"<secret>"}`；`JWT_ACTIVE_KID` = `k1`。

---

## 2. 推程式碼到 GitHub（私有 repo 已存在）

目前 G 層（T15–T19）＋部署設定尚未 commit。推送前確認**無密鑰／真資料**入版控（`.gitignore` 已排除 `.env`、`*.xlsx`、`*.pdf`、`*.dump`）：

```powershell
cd C:\Users\larry0701\haoshi\repo
git status
git ls-files | Select-String -Pattern '\.env$|\.xlsx$|\.pdf$|secret|\.dump$'   # 應只有 .env.example
git add -A
git commit -m "feat(G): T15-T19 + demo 部署設定（跨站 cookie/noindex/使用者管理腳本）"
git push origin HEAD
```

---

## 3. Neon — 建 DB + 灌真資料

1. Neon 建立 **PostgreSQL 17** 專案，取得連線字串（形如
   `postgresql://<user>:<pass>@<ep>.<region>.aws.neon.tech/neondb?sslmode=require`）。
2. 從本機 dump（自訂格式）：
   ```powershell
   $bin = "C:\Users\larry0701\haoshi\pgsql\bin"
   & "$bin\pg_dump.exe" -U postgres -h localhost -Fc -f "C:\Users\larry0701\haoshi\haoshi_dev.dump" haoshi_dev
   ```
3. 還原到 Neon（用 Neon 連線 URI）：
   ```powershell
   & "$bin\pg_restore.exe" --no-owner --no-acl -d "postgresql://<user>:<pass>@<ep>.aws.neon.tech/neondb?sslmode=require" "C:\Users\larry0701\haoshi\haoshi_dev.dump"
   ```
   > dump 含 schema＋資料＋`alembic_version`＋`btree_gist` 擴充＋GiST exclusion 約束。還原後 Neon 即為 head。
   > 少量 `--no-owner` 相關 NOTICE 可忽略。
4. **後端要用的 DATABASE_URL**（注意 driver 前綴 `+psycopg`）：
   ```
   postgresql+psycopg://<user>:<pass>@<ep>.aws.neon.tech/neondb?sslmode=require
   ```

---

## 4. Render — 部署後端（FastAPI）

New → **Web Service** → 連 GitHub repo `Yang890701/-`。

| 設定 | 值 |
|---|---|
| Root Directory | `api` |
| Runtime | Python（環境變數 `PYTHON_VERSION` = `3.13.4`） |
| Build Command | `pip install -r requirements.txt && alembic upgrade head` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance | Free |

**環境變數（Environment）**：

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...neon.../neondb?sslmode=require`（步驟 3） |
| `JWT_SIGNING_KEYS` | `{"k1":"<secret>"}`（步驟 1） |
| `JWT_ACTIVE_KID` | `k1` |
| `AUTH_COOKIE_SECURE` | `true` |
| `AUTH_COOKIE_SAMESITE` | `none`（前後端跨網域必需） |
| `CORS_ALLOWLIST` | 先填 `https://example.vercel.app`，步驟 6 再改成真 Vercel 網域 |

部署完成取得後端 URL：`https://<render-app>.onrender.com`。驗證 `GET /health` 回 `{"status":"ok"}`。

> 附件上傳：free 方案磁碟為暫存，重啟後上傳檔會消失（demo 不展示上傳即可）。

---

## 5. Vercel — 部署前端（Next.js）

Add New → **Project** → 匯入 GitHub repo `Yang890701/-`。

| 設定 | 值 |
|---|---|
| Root Directory | `web` |
| Framework | Next.js（自動偵測） |
| Environment Variable | `NEXT_PUBLIC_API_BASE` = `https://<render-app>.onrender.com` |

> `NEXT_PUBLIC_*` 於 **build 期**注入；若之後改後端網址，需 **redeploy** 前端。

部署完成取得前端 URL：`https://<vercel-app>.vercel.app`。

---

## 6. 串接 + 換帳密 + 冒煙

1. **回填 CORS**：Render 的 `CORS_ALLOWLIST` 改成真 Vercel 網域 `https://<vercel-app>.vercel.app` → 重新部署後端。
2. **換掉預設帳密 + 建合作對象帳號**（於 Render Shell，或本機設 `DATABASE_URL`=Neon 後跑）：
   ```powershell
   cd C:\Users\larry0701\haoshi\repo\api
   $env:DATABASE_URL="postgresql+psycopg://...neon.../neondb?sslmode=require"
   .\.venv\Scripts\python.exe -m scripts.manage_users set-password --username admin --password '<新強密碼>'
   # 給合作對象一個帳號；若只需看功能不看金流，用 staff（自動遮蔽 電話/租金/繳費）
   .\.venv\Scripts\python.exe -m scripts.manage_users create --username partner --password '<密碼>' --role staff
   ```
3. **端到端冒煙**（對公開 URL）：開 `https://<vercel-app>.vercel.app` → 用新帳號登入 → 首頁分區 → `/data` 查一張表 → `/billing` 建試算。確認登入後 refresh 不掉線（跨站 cookie 生效）。

---

## 環境變數總表（後端）

| Key | 預設 | 正式(demo) |
|---|---|---|
| `DATABASE_URL` | （必填） | Neon `+psycopg` URI |
| `JWT_SIGNING_KEYS` | 無 → 拒啟動 | `{"k1":"..."}` |
| `JWT_ACTIVE_KID` | 取第一把 | `k1` |
| `AUTH_COOKIE_SECURE` | `false` | `true` |
| `AUTH_COOKIE_SAMESITE` | `strict` | `none` |
| `CORS_ALLOWLIST` | `http://localhost:3000` | Vercel 網域 |

## 疑難

- **登入後一直被登出／refresh 401**：`AUTH_COOKIE_SAMESITE=none` 且 `AUTH_COOKIE_SECURE=true` 沒設全 → 跨站 cookie 沒送出。
- **CORS 被擋**：`CORS_ALLOWLIST` 必須完全等於 Vercel 網域（含 `https://`，無結尾斜線）。
- **Render 502 冷啟**：free 方案休眠，第一次請求等 ~30 秒屬正常。
- **pip 裝到不相容版本**：requirements 未鎖版；必要時以 `pip freeze` 產生鎖定版本再推。
