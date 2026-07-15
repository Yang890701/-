# A — 左側頁簽分組

實作：指揮方直接改（純前端小任務）。

## 改動
- `web/app/page.tsx`：新增 `TAB_GROUPS`（主檔=site/meter/room；帳務=meter_reading/avg_price/rent_confirm/exception_charge/room_fixed_fee；房客=tenant_contract），側欄改為分組渲染，未歸類者落「其他」（目前 mgmt_reminder）。
- `web/app/globals.css`：新增 `.side-group` / `.side-group-title` 樣式（低彩度小標題）。

## 驗收
- 後端 /health = ok；前端重新編譯 612 modules 無錯誤；`GET / 200`。
- 左側出現四組標題，10 表正確歸類（主檔3/帳務5/房客1/其他1=mgmt_reminder）。
- 純前端變更，未動 API/資料/元數據。

狀態：done（待使用者瀏覽器目視確認樣式）。
