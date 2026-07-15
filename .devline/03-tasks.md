# 03-tasks — 任務單（九欄 Loop Spec 精簡版）
<!-- 頭部遙測：2026-07-15｜Fable 5｜約耗 token ~210k。狀態: todo/doing/done/blocked -->
<!-- 輸入：01-spec v2、02-constitution v2、02-architecture v3。里程碑：M=DMO展示(T1-T14)；G=Go-live切換(T15-T21)；部署 T22(站7)。 -->
<!-- 實作順序(web-system型別)：資料層→後端(含fallback)→前端→整合；每層先 hello-world 驗通才長肉。 -->

## Phase 0 — 骨架
| id | 目標（一句話） | 驗收（可執行） | 邊界（不准動什麼） | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T1 | monorepo 骨架：web(Next.js+TS+TanStack+SheetJS)、api(FastAPI+pydantic，本機 py3.14 venv)、本機用**原生 PostgreSQL**+物件儲存以本地資料夾 adapter 模擬、.env.example；docker-compose(pg+minio)保留供機器A(選A)用 | 原生 PG 連得上；`alembic upgrade head` 成功；`uvicorn` /health 回200；`npm --prefix web run build` 綠 | 不寫業務邏輯，只 hello-world | codex | **done** | evidence/T1.md |
| T2 | lint/format 基線：ruff(api)+prettier/tsc(web) | ruff/tsc/prettier 全綠 | — | sonnet | **done** | evidence/T2.md |

## Phase M（DMO）— 資料層
| id | 目標 | 驗收 | 邊界 | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T3 | PostgreSQL schema(Alembic)：13 域表+系統表(app_user/table_meta/column_meta/audit_log/job/attachment/user_scope)+enum_*+匯入staging(stg_*/import_batch/import_row_error/legacy_key_map)；surrogate PK/partial unique(deleted_at is null)/room_meter_assignment exclusion constraint/型別紀律(電號TEXT,billing_ym CHAR(6)) | `alembic upgrade head` 成功；`\d room_meter_assignment` 見 exclusion constraint；電號欄型 text；partial unique 存在 | 不含業務計算 | codex | **done** | evidence/T3.md |
| T4 | 匯入管線：4 Excel→staging→清洗14地雷(補零/民國→西元/enum_map/度數表join鍵重建/軟刪)→正式表 + import_batch 對帳報表(來源/匯入/排除+原因/null/orphan/金額總和/前導零/民國異常)+import_row_error+legacy_key_map | 跑匯入→對帳報表各表列數與來源±已知髒值一致；抽20列比對Excel；電號前導零完整；民國異常清單產出 | 不動來源 Excel(唯讀) | codex | **done** | evidence/T4.md |

## Phase M（DMO）— 後端核心
| id | 目標 | 驗收 | 邊界 | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T5 | 認證：argon2+JWT(access短效+kid)+refresh(DB hash可撤銷+token_version)+login lockout+logout | 正確登入得access+refresh；錯密碼N次鎖定；refresh換access；logout後refresh失效(**負向測試**) | — | codex | **done** | evidence/T5.md |
| T6 | 授權中介層：角色(admin/manager/accounting/staff+readonly)+欄位級+**row-level scope(user_scope自動注入)**〔Codex必測①〕 | **負向測試**：staff只得其scope的列；敏感欄不現於response/filter/sort/export；越權表/欄回403 | — | codex | **done** | evidence/T6.md |
| T7 | 元數據：table_meta/column_meta allowlist+code→受控physical(禁raw SQL)+運算子白名單+變更version/diff/actor/rollback+敏感欄二階段確認〔Codex必測⑤〕 | 設 column filterable=true→篩選器出現(重載生效、不改碼)；任意未登錄table/column字串→拒絕(**負向**) | — | codex | **done** | evidence/T7.md |
| T8 | 通用查詢/匯出：POST /api/data/{t}/query(filters/sort/page/size JSON schema)+POST /export(xlsx≤50k,同filter/sort,exportable欄,寫審計) | 5類篩選(文字exact/contains/列舉/日期區間/數字區間/空值)各比對DB COUNT；匯出列數=畫面；電號/電話文字無科學記號 | 查詢只走元數據allowlist | codex | **done** | evidence/T8.md |
| T9 | 審計：audit_log(DB≥1年)記登入/查詢匯出/CRUD/元數據變更/審計查詢；GET /api/audit(本查詢亦寫審計) | 各動作後audit_log有列；/api/audit查詢後亦生審計列 | — | sonnet | **done** | evidence/T9.md |
| T10 | 附件二段式：presign→attachment→attachment_id+MIME/大小限制+短效簽名讀取 | presign得URL；上傳後attachment_id可讀回；超限/錯MIME拒絕 | — | codex | **done** | evidence/T10.md |

## Phase M（DMO）— 前端　★T1-T14 完成＝DMO 里程碑(匯入快照可看/篩/匯出+登入分權審計)
| id | 目標 | 驗收 | 邊界 | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T11 | 前端骨架+登入頁+版面(無AI感視覺baseline:米色#f6f4f0/白卡/思源黑體/低彩度主色/淺陰影) | build綠；登入頁符合美學rubric三規則(色/字/形)；登入後進主框 | 不用紫藍漸層/發光/emoji功能圖示 | codex | **done** | evidence/T11.md |
| T12 | 通用檢視頁(TanStack Table,讀/api/meta渲染,伺服器端分頁排序,不硬編碼欄位) | 選繳租確認明細顯示分頁(50/頁)中文欄名可排序；切房客資料表同元件正常 | 欄位一律來自元數據 | codex | **done** | evidence/T12.md |
| T13 | 篩選器+匯出(依column_meta動態生成篩選器;匯出當前條件xlsx) | 案場+帳單年月篩選→列數對；匯出xlsx開啟列數=畫面、中文欄名 | — | codex | **done** | evidence/T13.md |
| T14 | 審計檢視頁 | 顯示審計列,依type/range過濾 | — | sonnet | **done** | evidence/T14.md |

## Phase G（Go-live 必備）— 主檔與電費
| id | 目標 | 驗收 | 邊界 | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T15 | 主檔CRUD(site/meter/room):表級+欄位級寫入權限,FK校驗,partial unique,軟刪歷史可查,審計 | 新增房號現於檢視；停用預設不顯示但歷史可查；建不存在案場的房號擋下；同自然鍵重複擋下 | — | codex | todo | evidence/T15.md |
| T16 | 房↔電表關聯:room_meter_assignment+meter_event(換表)+上傳度數/電價(接attachment)+reading_kind+reading_exception+「須先傳前期」〔Codex必測③〕 | **exclusion constraint防區間重疊(負向)**；換表接續正常；缺前期擋下；缺值進exception佇列 | — | codex | todo | evidence/T16.md |
| T17 | 電費引擎(async job):billing_run狀態機+idempotency_key+(billing_ym,scope)互斥鎖+input_snapshot+三模式(一般/景平合併/總電費拆帳)+四捨五入整數元+detail/charge_line〔Codex必測②〕 | golden_case三模式各≥3筆通過；同run重觸發被鎖擋(冪等,**負向**)；≥3既有月份全量重算 總筆數/總電費/每案場小計對帳、單筆≤1元 | 電費為程式碼實作,非元數據 | opus | todo | evidence/T17.md |
| T18 | 電費發布→應收:publish(draft→calculated→approved→published→reversed)落rent_confirm(唯一鍵room_id+billing_ym+charge_type+run_version)+沖銷反向帳+publish後不可變〔Codex必測②〕 | publish產生rent_confirm；重複publish擋(**負向**)；reversed產反向帳不刪原 | — | codex | todo | evidence/T18.md |
| T19 | 繳租確認頁+狀態機UI | 對某房某期生成明細,金額=房租+電費+固定費+例外款；狀態轉移寫審計 | — | codex | todo | evidence/T19.md |

## Phase G — 切換
| id | 目標 | 驗收 | 邊界 | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T20 | 切換runbook工具:最後delta import+最終對帳報表+凍結/回滾腳本+RPO/RTO記錄〔Codex必測④〕 | 演練跑delta+對帳全綠；回滾腳本可切回舊入口；回滾後資料歸屬程序驗證 | 不可逆動作先問(鐵律⑤) | codex | todo | evidence/T20.md |
| T21 | 備份還原演練+物件儲存版本化 | restore drill成功並記錄RPO/RTO | — | sonnet | todo | evidence/T21.md |

## 站7 部署（成本檔次前定）
| id | 目標 | 驗收 | 邊界 | 模型 | 狀態 | 證據 |
|---|---|---|---|---|---|---|
| T22 | 部署雙方案(精省/標準)+環境變數+CORS/CSP/rate limit/CSRF | 選定檔次部署→公開URL /health 200；安全標頭到位 | 部署=不可逆,先過permission-architect+使用者確認 | codex | todo | evidence/T22.md |

## 派工紀律
- `codex`＝站4 主力(codex exec)；`sonnet/haiku/opus`＝Claude(Agent tool，照 DISPATCH §0)。Codex 額度盡→降級 Claude subagent 照分級(使用者已同意)。
- 驗收不自驗(加嚴)：實作者交付→指揮方親跑驗收+read-back 抽查→才標 done。
- 同一任務連錯 2 輪→JUDGMENT §4 方向檢查→換拆法或升級(opus 接手)。
- Codex 點名 5 必測項落點：①T6 row-scope ②T17/T18 billing鎖/冪等/publish ③T16 exclusion constraint ④T20 cutover演練 ⑤T7 metadata治理。
