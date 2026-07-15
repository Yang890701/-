# 02-architecture — 架構書 v2（與憲法同過 GATE-A；實作契約之源）
<!-- 頭部遙測：2026-07-15｜Fable 5｜約耗 token ~185k。v2=吃進 GATE-A 第1輪 24 條 findings（含完整電費/切換模型） -->
<!-- 原始欄位定義見 scratchpad/data-analysis.md（13 表 + 關聯驗證）。本檔為契約層。 -->

## 元件圖（文字版：誰呼叫誰、資料流向）
```
[Next.js 前端(SSR/CSR)]
   │ 依角色渲染：讀 /api/meta 決定表/欄/篩選器/可否匯出；不硬編碼欄位；不承載業務邏輯
   ▼
[FastAPI /api]
   ├─ 中介層：JWT 驗證 → 角色/欄位級授權 → 元數據 allowlist 解析(code→受控 physical key)
   ├─ 唯讀查詢/匯出 ─▶ [PostgreSQL]（select/filter/sort/export 一律套同一份 column 權限）
   ├─ 業務命令(CRUD/上傳/電費/繳租)：程式碼實作，非元數據驅動 ─▶ [PostgreSQL](交易)
   ├─ 附件：presign ─▶ [私有物件儲存]，業務只收 attachment_id
   ├─ 長任務(匯入/電費/大匯出) ─▶ [job 表 + worker]（精省=同服務背景/標準=獨立 worker；API 契約一致）
   └─ 每次 登入/查詢匯出/CRUD/元數據變更/審計查詢 ─▶ audit_log(DB, ≥1年)

[匯入管線] Excel ─▶ [stg_* / raw JSONB] ─(清洗14地雷+enum_map)─▶ 正式表 + import_batch對帳報表 + import_row_error + legacy_key_map
[元數據 table_meta/column_meta] ── 驅動 ──▶ 前端渲染 & 後端查詢白名單（只控檢視/篩選/匯出）
(過渡期正式源=SharePoint/n8n；新系統僅驗證；G 當日切換、之後禁 n8n 寫入)
```

## API 契約
### 認證與授權
| 端點 | 方法 | 請求 | 回應 | 備註 |
|---|---|---|---|---|
| /api/auth/login | POST | {username,password} | {access(短效),user} + Set-Cookie(refresh, httpOnly/secure/sameSite=strict) | 失敗鎖定(N次)；密碼 argon2/bcrypt |
| /api/auth/refresh | POST | (cookie refresh) | {access} | refresh 存 DB hash 可撤銷；比對 token_version |
| /api/auth/logout | POST | — | 204 | 撤銷 refresh；bump 可選 |
- access token：Authorization: Bearer，短效 TTL(~15–30min)，置記憶體(不落 localStorage)；JWT 帶 `kid` 支援金鑰輪替；`token_version` 變更即失效舊 token。
- 安全標頭：CSP、rate limit、CORS 白名單、CSRF token(對 cookie 型變更請求)。

### 元數據（只控檢視/篩選/匯出）
| 端點 | 方法 | 回應 |
|---|---|---|
| /api/meta/tables | GET | 依角色可見表 [{code,label}] |
| /api/meta/tables/{t}/columns | GET | [{code,label,type,filterable,operators[],exportable}]（已依角色遮罩） |

### 資料查詢/匯出（修正 #1-3：POST + JSON schema + 全套欄位權限）
| 端點 | 方法 | 請求(JSON) | 回應 | 授權 |
|---|---|---|---|---|
| /api/data/{t}/query | POST | {filters:[{col,op,val}], sort:[{col,dir}], page, size} | {rows(敏感欄遮罩), total} | table.read_roles；每 col 檢查 read/filter/sort_roles；op 限白名單 |
| /api/data/{t}/export | POST | {filters,sort} | xlsx(≤50k列，套同 filter/sort，只出 exportable 欄，寫審計) | table+col.export_roles |
- **鐵則**：不可見/未授權欄位一律拒絕出現在 select/filter/sort/export；`code` 只映射到受控 physical column 或固定查詢模板，**元數據不存 raw SQL**。

### 主檔 CRUD（修正 #9：表級+欄位級寫入權限）
| 端點 | 方法 | 備註 |
|---|---|---|
| /api/master/{t} | POST/PUT/DELETE | 依 table.create/update/delete_roles + 欄位 write_roles；FK 校驗；自然鍵 unique；軟刪(歷史仍可查)；寫審計 |

### 附件（修正 #10：二段式）
| 端點 | 方法 | 備註 |
|---|---|---|
| /api/attachments/presign | POST | {kind,mime,size}→{attachment_id, presigned_put_url}；限 MIME(jpg/png/pdf)+大小 |
| (業務 API) | — | 只收 attachment_id；讀取走短效簽名 URL |

### 電費/繳租（修正 #5,6,7,15：async job + 可重現）
| 端點 | 方法 | 備註 |
|---|---|---|
| /api/meter-readings | POST | {room_meter_assignment_id,帳單年月,reading_kind,度數,attachment_id}；缺前期擋下 |
| /api/avg-prices | POST | {meter_id,帳單年月,平均電價,attachment_id} |
| /api/billing/runs | POST | {billing_ym,scope}→建立 async job，回 {run_id,status} |
| /api/billing/runs/{id} | GET | {status,summary}（狀態:queued/running/done/failed） |
| /api/billing/runs/{id}/details | GET | 分頁逐房逐項明細 |
| /api/rent-confirm | POST | {room_id,billing_ym,...}→狀態機轉移；唯一鍵防重複；金額異動保版本 |
| /api/audit | GET | ?type&range；**本查詢亦寫審計** |
| /api/jobs/{id} | GET | 通用 job 狀態(匯入/大匯出/電費共用) |

## 資料模型（surrogate PK；自然鍵 unique；完整欄位見 data-analysis.md）
> 通則(修正#8,12)：所有表 PK=surrogate `id`；自然鍵(案場/電號/房號…)為 UNIQUE；保留 `legacy_key/source_key`；`billing_ym CHAR(6)` YYYYMM；代碼欄 TEXT 保前導零；日期 DATE；軟刪 boolean 預設過濾。

| 群 | 表 | 自然鍵(unique) | 關鍵 FK/索引 | 備註 |
|---|---|---|---|---|
| 主檔 | site 案場 | 案場 | — | |
| 主檔 | meter 電號 | 電號 | — | |
| 主檔 | room 房號 | 房號 | site_id | 含電費計算類型(一般/總電費拆帳/總電表與子電表) |
| 主檔 | **room_meter_assignment** | (room_id,電表類別,eff_from) | room_id,meter_id | **有效年月區間**連結房↔電表↔類別+初始/終止度數；支撐歷史重算與換表(修正#7) |
| 帳務 | meter_reading 度數 | (assignment_id,帳單年月,reading_kind) | assignment_id | +`reading_kind`(初始/例行/補登/換表)；join鍵重建(修正#6) |
| 帳務 | **meter_event** 換表事件 | — | assignment_id | 換表/停用/初始，記 old/new reading(修正#6) |
| 帳務 | **reading_exception** 缺值例外 | — | assignment_id,帳單年月 | 漏抄/異常待處理佇列 |
| 帳務 | avg_price 平均電價 | (meter_id,帳單年月) | meter_id | |
| 帳務 | special_price 特殊電價 | room_id | room_id | 覆寫 |
| 帳務 | **billing_run** | (billing_ym,version) | created_by | async job；`input_snapshot`(讀數/價格快照 ref) → 可重現(修正#5) |
| 帳務 | **billing_run_detail** | (run_id,room_id) | run_id,room_id | 逐房計算結果 |
| 帳務 | **billing_run_charge_line** | — | detail_id | 逐項(房租/電費/固定費/例外款)+source_ref |
| 帳務 | **golden_case** | case_code | — | 三模式(一般/景平合併/總電費拆帳)期望值，回歸對帳(修正#5) |
| 帳務 | rent_confirm 繳租確認 | (room_id,billing_ym,charge_type,seq) | room_id | 狀態機(草稿/已確認/已匯出/作廢)；金額異動保版本(修正#16) |
| 帳務 | exception_charge 例外款項 | — | room_id | 含未來預排；區分應收期vs建檔 |
| 設定 | room_fixed_fee 固定費用 | (room_id,費用項目) | room_id | 費用項目走 enum |
| 房客 | **tenant_contract** 租約 | (room_id,起租) | room_id | 單一真相；歷史合約(修正#11) |
| 房客 | tenant_current(**view**) | — | — | =每房最新有效合約(view/matview，非雙寫) |
| 房客 | line_contact | Line ID | — | v1 不逐房；**預留** tenant_contact/room_contact_link(v2, 修正#21) |
| 設定 | mgmt_reminder 管理提醒 | — | site_id? target_id? | +target_type/target_id/site_id/due_date/status/created_by(修正#23) |
| 系統 | app_user | username | — | argon2；role；token_version |
| 系統 | table_meta / column_meta | code | — | allowlist；code→受控physical；表級+欄位級 read/filter/sort/export/create/update/delete_roles(修正#4,9) |
| 系統 | attachment | — | uploaded_by | kind/mime/size/object_key(修正#10) |
| 系統 | audit_log | — | actor | action/table/filters/rows/ts；**DB≥1年**(修正#19) |
| 系統 | job | — | — | 類型/狀態/retry/lock；匯入/電費/大匯出共用(修正#20) |
| 匯入 | stg_*/raw JSONB, import_batch, import_row_error, legacy_key_map | — | batch_id | staging+對帳+錯誤列+鍵映射+source file(修正#14) |
| 匯入 | enum_* + enum_map | — | — | 正式欄位用 enum table+FK/check；enum_map 僅 staging(修正#13) |

## 電費計算資料流（修正 #5,6,7；G 可重現對帳之本）
1. 找前期：由 `room_meter_assignment`(有效區間) + `meter_reading`(reading_kind) 定位同一 assignment 的前期讀數；換表/初始由 `meter_event` 提供起算基準。
2. 用量 = 本期度數 − 對應前期度數（初始月用 assignment.initial_reading）；缺值→ `reading_exception` 佇列，不硬算。
3. 電費 = 用量 × avg_price（或 special_price 覆寫）；三模式：一般 / 景平401-404 合併(多房共表加總) / 總電費拆帳。四捨五入至整數元(規則明訂於實作)。
4. `billing_run` 建立時凍結 `input_snapshot`(當下讀數+價格) → 每筆結果落 `billing_run_charge_line` 附 source_ref → **同輸入必得同結果**，供 golden case 與月度對帳。

## 部署拓撲（雙方案；API 契約不隨檔次改變，修正 #20）
- **精省**：1×Next.js + 1×FastAPI(內含背景 job runner + job 表 + retry/lock) + managed PostgreSQL + S3相容物件儲存；PaaS app log 90 天。
- **標準**：前後端分離 + 獨立 worker + managed PostgreSQL + 物件儲存(版本化)；PaaS log 90 天。
- **共同不可砍**：`audit_log` DB **≥1年**、DB 每日備份(≥7天)+**G前還原演練+記 RPO/RTO**、物件儲存備份/版本化(修正#19,24)。
- 環境變數(不入庫)：`DATABASE_URL / JWT_SIGNING_KEYS(含kid) / OBJECT_STORE_{KEY,SECRET,BUCKET,ENDPOINT} / CORS_ALLOWLIST`。
- 免費/低價方案休眠與 DB 到期限制記 log 供提醒。

## 非功能需求落點
- **安全**：JWT(短效access+可撤銷refresh+kid+token_version) + 角色/欄位級授權 + 元數據 allowlist(擋越權/注入) + CSP/CSRF/rate limit/lockout + 圖檔私有簽名URL，於 FastAPI 中介層。
- **效能**：POST 查詢+伺服器端分頁/排序 + 可篩排序欄索引 + 匯出上限50k + 長任務走 job/worker，後端+DB。
- **法遵/PII**：欄位遮罩(select/filter/sort/export 一致) + 去識別化截圖 + PII不入版控 + audit_log≥1年。
- **成本**：部署雙方案，檔次站7前拍；不可砍底線不受檔次影響。

## v3 追加（GATE-A 第2輪 7 條深層 findings）
### 授權範圍 row-level scope（r2#1，高）
- 新增 `user_scope`(user_id, scope_type[all/site/mgmt_unit], scope_value)；admin=all，manager/staff/accounting 可被限縮到特定 案場/管理單位。
- **所有** query/export/CRUD/audit 於中介層自動注入 row-scope predicate（不只欄位遮罩，還限「看得到哪些列」）；未設 scope 者預設最小權限。

### 電費 run 冪等與發布邊界（r2#2,#3，高）
- `billing_run` 狀態機：`draft → calculated → approved → published → reversed`；publish 後**不可變**，重算＝產生新 version（不覆寫）。
- 併發控制：同 `(billing_ym, scope)` 互斥鎖 + `idempotency_key`，防同月同房重算兩次/重複帳。
- **發布契約**：`billing_run publish` 時才把結果落成正式應收——寫 `rent_confirm`(唯一鍵 `room_id+billing_ym+charge_type+run_version`)；沖銷走 `reversed` 並產生反向帳，不直接刪。

### 切換 cutover 協議（r2#4，高；與 01-spec §切換 runbook 對齊）
- G 當日：舊系統 freeze 時間點 → 最後一次 delta import → 最終對帳清單全綠 → DNS/入口切換 → 禁 n8n 寫入。
- 回滾：定義觸發條件（登入不可用/電費對帳失敗/匯出錯誤）；**回滾後新系統已寫資料的歸屬與補回舊系統程序**須事先備妥。

### 時間區間完整性（r2#5，高）
- `room_meter_assignment` 用 DB **exclusion constraint** 保證同 room+電表類別的有效年月區間不重疊；換表為相鄰接續、合併房為明列允許例外。

### 元數據變更治理（r2#6，中）
- metadata 變更保 version/diff/變更人/可回滾；**敏感欄位權限變更走二階段確認**（防 admin 誤改即刻外洩）。

### 軟刪與唯一鍵（r2#7，中）
- 自然鍵 unique 改 **partial unique**（`WHERE deleted_at IS NULL`）；定義恢復軟刪資料時的衝突處理。

## GATE-A 紀錄
- 第1輪(gpt-5.5)：24條(高10/中11/低3)——見 log；四大風險=查詢旁路洩漏/電費無法重現/歷史電表關聯錯算/切換後鍵不可維護。
- 本 v2 逐條處置(A查詢安全~K雜項共11類)：POST查詢+全套欄位權限、metadata只控檢視且code→受控physical、surrogate PK+legacy_key、電費三新表+assignment+event+snapshot+golden_case、tenant_contract+current改view、匯入staging/error/keymap+enum table、二段式附件、auth生命週期、audit≥1年、job表跨檔次一致、reminder補欄。
- 第2輪：v2 收斂原24條，但挖出7條深層(高5/中2)——row-level scope、電費run冪等/發布邊界、cutover freeze/delta、assignment區間重疊、metadata治理、軟刪partial unique；已於「v3追加」段逐條處置。
- 第3輪：**Codex 核可進站3**，無擋進站3的高嚴重度 blocker。5 項務必在站3拆成明確實作+測試任務：①user_scope自動注入負向測試 ②billing_run鎖/冪等/publish不可變/reversed ③assignment exclusion constraint與換表/合併房例外 ④cutover演練(freeze/delta/reconcile/rollback) ⑤metadata變更version/diff/rollback+敏感欄二階段確認。
- 使用者定稿：**2026-07-15 核准進站3（無破例）**。
