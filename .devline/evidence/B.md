# B — 入口首頁重建（清單列表版）

實作：Codex（bcsx7lshy），指揮方親驗。

## 改動（只動 web/）
- `web/app/page.tsx`：`/` 改為入口首頁 PortalHomePage（清單列表，非按鈕格）。
- `web/app/data/page.tsx`：原資料檢視頁移此（行為不變：分組頁簽/篩選/分頁/匯出）。
- `web/app/portal-data.ts`：portal 連結分區(主檔管理/電費作業/資料查詢)+公告，typed 靜態種子。
- `web/app/providers.tsx`：共用導覽列 首頁/資料檢視/稽核（active 樣式）。
- `web/app/globals.css`：portal 清單/公告樣式（沿用米色/白卡/細邊框）。
- `web/next.config.ts`：pin outputFileTracingRoot（順修多 lockfile 警告）。

## 親驗
- `npm run build` 綠：路由 `/`、`/data`、`/audit`、`/login` 皆建置成功。
- Live dev server：`/`→200(33KB 入口頁)、`/data`→200、`/audit`→200。
- 連結：可用者(通用資料檢視→/data、稽核→/audit)可點；未建者(主檔/電費各頁)顯示「開發中」灰標不可點；未指回舊 SharePoint/n8n。
- 公告區含 2 則種子公告（置頂優先）。

狀態：done（待使用者瀏覽器目視確認樣式）。
