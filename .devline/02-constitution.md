# 02-constitution — 專案憲法（下游一切產出與本檔衝突，以本檔為準）
<!-- 頭部遙測：2026-07-15｜Fable 5｜約耗 token ~160k。GATE-A 通過後凍結：要改=回站2重走閘 -->

## 1. 技術棧定案
| 層 | 選擇 | 一句話理由 |
|---|---|---|
| 前端/介面 | Next.js(React) + TanStack Table + SheetJS + Noto Sans TC | 通用資料表/伺服器端分頁排序成熟；client 匯出 xlsx；SSR/路由完整 |
| 後端/核心 | FastAPI(Python) + Pydantic | 型別積木實戰驗證；DB 協作同事 Python 親和；請求/回應強型別 |
| 資料 | PostgreSQL | 關聯模型清晰、交易完整、索引/查詢成熟 |
| 圖檔 | 私有物件儲存(S3 相容，如 Cloudflare R2 / Backblaze B2) + 短效簽名 URL | 電表/帳單照含 PII，不可公開 |
| 部署 | 付費雲 PaaS，**精省/標準雙方案**（檔次站7部署前拍板） | 成本敏感，架構先包住兩檔次 |

## 2. 不可違背原則（違反任一＝實作退回）
1. **誠實資料**：示意/測試資料不得標成真實；PII 不進版控；對外展示/截圖去識別化。
2. **元數據驅動且白名單**：通用檢視/篩選/匯出由 `table_meta`/`column_meta` 驅動，且為 **allowlist**；後端只認已登錄 table/column 與運算子，拒任意字串（防越權/SQL 注入）。**禁第2層低代碼**（整頁版面/邏輯塞 DB）。
3. **元數據只控檢視/篩選/匯出**：各表可見欄/篩選器/匯出欄一律讀元數據(維護面靠改 DB)；但**業務命令(電費計算/狀態機/上傳/CRUD 業務規則)一律程式碼實作，不得元數據化/低代碼化**(修正 finding#4)。
4. **權限與審計**：授權含**欄位級**(敏感欄電話/租金/繳費，select/filter/sort/export 一致套用)＋**列級範圍**(row-level scope：非 admin 只能存取被授權的案場/管理範圍，自動注入 query/export/CRUD/audit)；匯出/CRUD/元數據變更/登入/審計查詢 一律寫審計；**`audit_log` 存 DB ≥1年(與 app log 90天分開)、DB 備份為不可砍底線**。金鑰後台填、不入庫。
5. **展示≠切換**：DMO(M) 可展示不代表可切換；Go-live(G) 需 M+G 全通過 + 匯入對帳 + 電費 golden 對帳 + 回滾演練；**過渡期 SharePoint/n8n 為唯一正式資料源**，G 後禁 n8n 寫入。
6. **電費可對帳**：電費計算須通過 ≥3 個既有月份全量重算對帳、單筆差異≤1 元或列例外、三種計算模式各≥3 筆 golden case；四捨五入/整數元規則明訂。
7. **型別/鍵紀律**：所有表 surrogate PK、自然鍵 unique、保留 `legacy_key/source_key`；代碼欄(電號/電話)一律 TEXT 保前導零；`billing_ym CHAR(6)` YYYYMM；民國年→西元 DATE 於匯入層轉；軟刪(DELFLAG)預設過濾、歷史查詢仍可查。

## 3. 明確的取捨（我們選了 X 放棄 Y，因為 Z）
- 選**全自建**放棄現成平台(Directus/NocoDB)：因需客製「無 AI 感」美學 + 對外房客 v2 + 電費商業邏輯；代價＝前端要寫碼，以「元數據層」把日常欄位/篩選/匯出維護留給 DB 同事。
- 選 **FastAPI** 放棄 NestJS：DB 協作者 Python 親和 + 型別積木既有驗證。
- **雙部署方案**暫不定死：成本敏感，精省/標準兩檔次留站7前拍，但不可砍底線先鎖。

## 4. 衝突裁決規則
下游（tasks/實作/測試）與本檔衝突 → 停工，回報使用者：改憲法（重走 GATE-A）或改下游。

## GATE-A 紀錄
- Codex 對審 第1輪：見 02-architecture 完整 24 條。**觸及本憲法且已於 v2 修訂**：原則3 收窄為「元數據只控檢視/篩選/匯出，業務命令程式碼實作」(finding#4)；原則4 明訂 audit_log DB ≥1年(finding#19)；原則7 補 surrogate PK/自然鍵 unique(finding#8)。
- 第2輪：新增7條深層findings，觸及本憲法者已改——原則4 納入 row-level scope。
- 第3輪：Codex 核可進站3(詳見 02-architecture)。
- 使用者定稿：**2026-07-15 核准，憲法凍結（無破例）**。要改憲法層級的決定＝回站2重走 GATE-A。
