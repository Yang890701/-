# log — 開發線流水帳（中斷續接的唯一入口；行格式勿自創）
<!-- 行格式：`[YYYY-MM-DD HH:MM] 站N 進|出|事件 ｜ 一句話 ｜ 裁決/破例(有才寫)` -->
<!-- 事件類型：進站/出站/GATE-R/GATE-A/對審輪N/破例/跳過站5/降級/恢復/憲法觸碰檢查 -->

[2026-07-15 00:48] 站0 進 ｜ 開站，型別=web-system；收編既有「好室開發」包租代管系統→全新技術棧重寫（動幅=重寫，走全管線站0起） ｜
[2026-07-15 00:48] 事件 ｜ 前期發現已完成：既有系統剖析(靜態HTML+JWT+SharePoint+n8n)、4份Excel資料模型(13表,關聯已交集驗證,報告見scratchpad/data-analysis.md)、業務流程+電費公式(O365手冊)、14項資料品質地雷 ｜
[2026-07-15 00:48] 事件 ｜ 使用者本輪已拍板(勿重問)：雙模式(內部員工+對外房客/房東)、全自建(Next.js+TanStack+SheetJS/FastAPI或NestJS/PostgreSQL+第1層元數據表)、無AI感美學、首個DMO=資料檢視頁(檢視/篩選/匯出xlsx) ｜
[2026-07-15 01:05] 站0 事件 ｜ 訪談收斂4未決：房客登入=v1先只做內部(v2再做)、部署=付費雲PaaS、DMO=通用檢視頁涵蓋所有表(元數據驅動)、過渡=一次切換 ｜ 後端定FastAPI
[2026-07-15 01:05] 站0 事件 ｜ 調和「v1只做內部×一次切換」：v1內部側三階段(①檢視/篩選/匯出DMO→②取代n8n的CRUD+電費計算→③一次切換)；開發期用匯入快照 ｜ 待GATE-R隨規格定稿確認範圍界線
[2026-07-15 01:05] 站0 出 ｜ 出站檢查全勾(目標/成功樣貌/不做4條/未決≤2) ｜
[2026-07-15 01:05] 站1 進 ｜ 寫規格(三方語言對照+可執行驗收)，準備GATE-R ｜
[2026-07-15 01:20] GATE-R 對審輪1 ｜ Codex(gpt-5.5)唯讀沙箱審01-spec，列13條findings(高4/中7/低2)：M/G里程碑混淆、電費驗收不可測、PII權限不足、回滾只一句、元數據越權、篩選/匯出/匯入驗收不足、CRUD軟刪語意、圖檔安全、繳租狀態機、美學/成本NFR缺 ｜
[2026-07-15 01:35] GATE-R 事件 ｜ 規格改v2逐條處置13條(拆M/G+Go-live條件、電費golden對帳、權限矩陣、切換runbook、元數據allowlist、匯入對帳報表、狀態機、私有bucket、美學具體規則、NFR) ｜
[2026-07-15 01:40] GATE-R 對審輪2 ｜ Codex resume確認v2已收斂、無擋進站2高嚴重度；留3項進站2前釘死(過渡期資料權威源已補runbook#0/角色權限升架構阻斷/月費日誌雙方案+不可砍底線) ｜
[2026-07-15 01:40] GATE-R 待 ｜ 卡在使用者定稿(step③點頭)+2項架構阻斷決策(角色權限、月費日誌上限) ｜ 未過閘不得進站2
[2026-07-15 01:55] GATE-R 過 ｜ 使用者核准進站2(無破例)；角色定4+1(staff不見電話/租金/繳費)；成本「使用者我來定」→站2做精省/標準雙方案、檔次站7前拍 ｜
[2026-07-15 01:55] 站1 出 ｜ 01-spec.md v2 定稿 ｜
[2026-07-15 01:55] 站2 進 ｜ 產出02-constitution(技術棧+不可違背原則)+02-architecture(元件圖/API契約/資料模型/雙部署方案)，準備GATE-A ｜
[2026-07-15 02:15] GATE-A 對審輪1 ｜ Codex審憲法+架構列24條(高10/中11/低3)；四大風險=查詢旁路洩漏/電費無法重現/歷史電表關聯錯算/切換後鍵不可維護；11項v2修正清單已記入02-architecture GATE-A節(A查詢安全~K雜項) ｜
[2026-07-15 02:15] GATE-A 待 ｜ 檢查點：v2修正清單待套用(尚未處置)→改完跑輪2→使用者定稿；未過GATE-A不得進站3/實作，憲法未凍結 ｜ 續接從02-architecture「v2待套用修正清單」起
[2026-07-15 02:20] 決策 ｜ 使用者選B：完整吃24條(含電費/切換完整模型)收斂到過閘；Codex額度用盡→降級fresh-context Claude審查+Claude subagent實作(devline降級協議) ｜
[2026-07-15 02:40] GATE-A 事件 ｜ 架構+憲法改v2吃進24條(11類A-K)；憲法原則3/4/7調整 ｜
[2026-07-15 02:45] GATE-A 對審輪2 ｜ Codex確認原24條收斂，新挖7條深層(高5/中2)：row-level scope/電費run冪等發布/cutover freeze-delta/assignment區間重疊/metadata治理/軟刪partial unique ｜
[2026-07-15 02:55] GATE-A 事件 ｜ 架構改v3吃進7條(v3追加段)；憲法原則4納row-level scope ｜
[2026-07-15 03:00] GATE-A 對審輪3 ｜ **Codex核可進站3**，無高嚴重度blocker；5項務必於站3拆成實作+測試任務 ｜ Codex共3輪達收斂(devline上限)
[2026-07-15 03:00] GATE-A 待 ｜ 卡在使用者定稿(step③點頭)→點頭後憲法凍結、進站3拆解 ｜
[2026-07-15 03:10] GATE-A 過 ｜ 使用者核准(無破例)，**憲法凍結**；改憲法層級=回站2重走閘 ｜
[2026-07-15 03:10] 站2 出 ｜ 02-constitution v2 + 02-architecture v3 定稿凍結 ｜
[2026-07-15 03:10] 站3 進 ｜ 拆task單(DMO/M層優先，G層在後)，含Codex點名5必測項 ｜
[2026-07-15 03:20] 站3 出 ｜ 03-tasks.md 22任務(Phase0 T1-2/M層T3-14=DMO里程碑/G層T15-21/部署T22)，模型標籤+驗收+5必測落點齊 ｜
[2026-07-15 03:20] 站4 待 ｜ 準備進實作(Codex主力,額度盡降級Claude)；先確認本機環境(Node/pnpm/Python/Docker)+使用者開工green light；T1骨架起 ｜
[2026-07-15 03:30] 站4 環境 ｜ 本機:Node24/Python3.14/git✅;pnpm缺(corepack解);Docker缺;無Postgres;winget✅ ｜ Python3.14太新→後端用3.12/3.13 venv
[2026-07-15 03:30] 決策 ｜ 使用者選B(本機原生PostgreSQL,物件儲存用本地資料夾模擬);之後另一台機器用A(Docker)。T1已調整:docker-compose保留供機器A ｜
[2026-07-15 03:30] 站4 blocked ｜ 卡在使用者安裝原生PostgreSQL(系統安裝需其手動/UAC)；裝好回報psql版本+超級使用者密碼設定→我建dev DB/角色→開T1 ｜
[2026-07-15 03:45] 站4 環境就緒 ｜ 使用者背景winget裝好PostgreSQL 17.10(服務postgresql-x64-17 running/5432)；winget靜默安裝超級密碼=預設'postgres'(待改，僅本機dev)；已建 haoshi_dev DB + haoshi 角色(dev密碼haoshi_dev_pw)登入驗證通過 ｜
[2026-07-15 03:45] T1 doing ｜ Codex(bvfym1q85)建好骨架:web(Next15+React19+TanStack+SheetJS)/api(FastAPI /health+storage本地adapter+alembic env讀DATABASE_URL)/infra/docker-compose(機器A用)/.env.example/README；schema/auth正確延後T3+；read-back關鍵檔通過 ｜ 驗收背景跑(web:beajsddou npm build／api:bc2w3s5wb venv+pip+alembic+health)
[2026-07-15 03:45] 待驗 ｜ DATABASE_URL=postgresql+psycopg://haoshi:haoshi_dev_pw@localhost:5432/haoshi_dev；py用3.14(venv)先試,失敗再裝3.12 ｜
[2026-07-15 04:00] T1 done ｜ 驗收全綠：web build✅(Next15.5.20)/py3.14依賴全裝✅(不用退3.12)/alembic連PG✅/health {"status":"ok"}✅；證據 evidence/T1.md ｜ 未commit(待使用者要求才commit)
[2026-07-15 04:00] T3 doing ｜ 派Codex建SQLAlchemy models+Alembic遷移(13域表+系統表app_user/table_meta/column_meta/audit_log/job/attachment/user_scope+enum表+匯入staging；surrogate PK/partial unique(deleted_at is null)/room_meter_assignment GiST exclusion防區間重疊/TEXT代碼/billing_ym CHAR(6))；Codex作者、我親跑alembic upgrade head驗收 ｜
[2026-07-15 04:20] T3 done ｜ 親跑驗收全綠:alembic head/48表/btree_gist/exclusion約束定義正確/27個partial unique/tenant_current view/electricity_code=text/billing_ym=char(6)/schema測4-4；證據evidence/T3.md ｜ exclusion活體負向測試排T16
[2026-07-15 04:20] T4 doing ｜ 派Codex建匯入管線(4 Excel→stg_*→清洗14地雷→正式表+import_batch對帳報表+import_row_error+legacy_key_map)；Codex作者、我親跑對帳驗收 ｜ 使用者要求做完T4回報
[2026-07-15 04:40] T4 親驗 ｜ Codex匯入跑通(site125/meter173/room668/avg_price301/meter_reading1660/rent_confirm1816/153錯誤列)；但親查揪3缺陷:①avg_price.price=integer小數電價被四捨五入(值4,3,3→應NUMERIC)②6真房因占位電號被丟+連累三重0314合約orphan③76筆空帳單年月rent_confirm+25筆空起租日合約被丟(應null匯入)。前導零✅保留 ｜ 不修不標done
[2026-07-15 04:45] T4-fix doing ｜ 派Codex修正輪(bnd6lzjrb):avg_price/special_price改NUMERIC(10,4)+新遷移、房間占位電號→meter_id NULL不丟、空欄以null匯入不丟、景平401-404合併表留error標deferred-to-T16；re-import後我親驗 ｜
[2026-07-15 05:10] T4-fix 使用者決策 ｜ codex修正輪黑箱久跑無輸出,使用者選A由我接手;停codex(未動任何檔,乾淨)→我親自改models(avg/special price→Numeric,billing_ym/lease_start_date nullable)+寫遷移0002+改importer 8處(補_decimal/房間空電號保留/空欄null匯入/景平deferred)+補openpyxl到requirements+修null-start去重撞legacy_key ｜
[2026-07-15 05:30] T4 done ｜ 親驗全綠:room 668→674/rent_confirm 1816→1898/tenant_contract 725→754/room_fixed_fee 177全入/avg_price小數保留(4.2000..)/error 153→23(僅真髒+景平deferred);金額sane;schema測4-4;alembic 0002 head；證據evidence/T4.md ｜
[2026-07-15 05:30] 站4 T5 doing ｜ 使用者指示T4後做T5(認證)：argon2+JWT(access短效+kid)+refresh(DB hash可撤銷+token_version)+login lockout+logout ｜
[2026-07-15 06:00] T5 驗收紅旗 ｜ Codex宣稱11測OK但輸出有1 FAILED,且因沙箱無網路裝不了httpx→自寫httpx2.py假shim讓TestClient跑(不可信)。處置:裝真httpx0.28.1、確認httpx2無引用(孤兒)→刪、真httpx重跑→11/11全過(FAILED是假shim假陰性)。httpx列入requirements、清openpyxl重複 ｜
[2026-07-15 06:10] T5 done ｜ live HTTP親驗全綠:login admin/admin123→200+JWT+refresh cookie;/me valid200/garbage401;refresh發新;logout204→再refresh401(撤銷);lockout連6錯=401×4,423,423(門檻5),鎖後正確密碼仍423;alembic 0003 head;refresh_session表+app_user鎖定欄齊;admin鎖定已重置。證據evidence/T5.md ｜ 正式須換JWT強金鑰+cookie secure
[2026-07-15 06:10] 進度 ｜ 完成:T1骨架/T3 schema/T4匯入/T5認證。待:T2 lint、T6授權中介層(row+欄位級,DMO關鍵)、T7主檔CRUD、T8通用查詢、T11-14前端→DMO ｜
[2026-07-15 06:20] 決策 ｜ 使用者:「全部做完再回報」→ 自主衝到DMO可動(檢視/篩選/匯出xlsx)。相依序:T7元數據→T6授權→T8查詢/匯出→T9審計→T11-14前端；T10附件屬上傳(G)延後;T2 lint最後;G層(T15-21)+部署T22(不可逆需使用者確認)不在本波 ｜
[2026-07-15 06:20] T7 doing ｜ 派Codex(bd3sbvik1)建元數據resolver(allowlist/運算子白名單/禁raw SQL)+seed table_meta/column_meta(10 DMO表,中文標籤,敏感欄contact_phone/rent非staff)+governance change_log(遷移0004)+meta端點+負向測試 ｜
[2026-07-15 06:40] T7 done ｜ 親驗:test_meta 3/3、alembic 0004、table_meta10/column_meta56、敏感欄contact_phone/rent/rent_confirm金額 read/export={admin,manager,accounting}排除staff、一般欄含全角色、tenant_contract staff見6/admin見8；Codex未再造shim。證據evidence/T7.md ｜ resolver活體負向測留T8
[2026-07-15 06:40] T6 doing ｜ 派Codex建授權中介層:角色依賴+user_scope列級範圍(依案場)+欄位遮罩helper(用column_meta read_roles)+單元測試 ｜
[2026-07-15 07:00] T6 done ｜ 親跑test_authz 4/4(含site-scoped staff只見自己案場=必測①)、全後端18測OK；site連結登記合理(各表→案場,meter/avg_price安全deny)。證據evidence/T6.md ｜
[2026-07-15 07:00] 更正 ｜ 我初判「Codex竄改starlette」錯誤:查證starlette1.3.1從PyPI乾淨重裝仍import httpx2,且httpx2 2.6.0是真實套件(httpx後繼)→Codex未竄改,import httpx2是正牌相依;Codex的httpx2.py只是無網路克難替代(已刪)。已裝真httpx2、requirements改httpx2、警告消失 ｜ 教訓:別急著扣「竄改」帽子,先查PyPI
[2026-07-15 07:00] T8 doing ｜ 派Codex建通用查詢/匯出:POST /api/data/{t}/query(用T7 resolver+T6 scope+欄位遮罩)+/export xlsx≤50k寫審計 ｜
[2026-07-15 07:20] T8 done ｜ test_data 5/5;live驗證:rent_confirm 202606 API total679=DB679、匯出xlsx中文標題+679列+寫審計1。DMO後端端到端可用。證據evidence/T8.md ｜
[2026-07-15 07:20] 前端 doing ｜ 派Codex建DMO前端(T11-13合併):登入頁+版面(無AI感)+通用檢視頁(讀/api/meta+/api/data/query分頁表)+篩選UI(依column_meta)+匯出鈕(呼/export下載xlsx)；驗收build綠+dev server起+頁面串真API ｜
[2026-07-15 08:00] 前端紅旗 ｜ Codex沙箱跑不了next build(卡住+殭屍node,只驗tsc);我清node/.next親跑build→通過。另揪CORS漏洞:Codex有cors_allowlist設定卻沒掛CORSMiddleware→瀏覽器會被擋;我在main.py補CORS(allow_origins=cors_allowlist,credentials)→預檢200+正確標頭 ｜
[2026-07-15 08:10] T11-13 done ｜ DMO前端上線:build綠、前後端常駐(:8000/:3000)、CORS通、login→meta(10表中文)→query(679=679)→export xlsx已驗;無AI感樣式。證據evidence/T11.md ｜ 限:互動UI未瀏覽器click-through(本環境無瀏覽器),待使用者開啟確認最後一哩
[2026-07-15 08:10] DMO里程碑 ｜ 核心DMO(檢視/篩選/匯出xlsx+登入分權審計)可動。M層剩:T9審計端點/T14審計頁/T10附件(上傳,G向)/T2 lint。G層T15-21+部署T22(不可逆)另議 ｜
[2026-07-15 09:00] T9/T10 done ｜ 親驗後端全測試29/29、遷移0005、live /api/audit(login/query/export/audit_query皆記)+附件presign(壞MIME拒/正確回簽章URL)。證據evidence/T9.md ｜ psycopg測試連線未關warning(小疵)
[2026-07-15 09:10] T14 done ｜ web build綠+/audit路由(admin-only,篩選/分頁);證據evidence/T14.md ｜
[2026-07-15 09:20] T2 done ｜ api ruff All checks passed!+format 39檔+測試29/29;web prettier+tsc lint綠。證據evidence/T2.md ｜
[2026-07-15 09:30] M層完成 ｜ T1-T14+T2全done。乾淨重啟後端到端live驗:health ok/login/10表/query=DB(rent_confirm679=679,room31=31)/匯出xlsx197KB/審計寫入/前端 //login//audit 皆200 ｜ 服務常駐:後端bx2flj6zy(:8000) 前端bq6ns3tte(:3000)
[2026-07-15 09:30] 待辦 ｜ G層(T15主檔CRUD/T16房電表/T17電費引擎/T18發布/T19繳租/T20切換/T21備份)+站7部署T22(不可逆,需使用者定成本檔次+點頭)。憲法凍結中,G層動工前無需重閘(未觸憲法) ｜
