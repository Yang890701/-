"use client";

// Genie — 全站右側 AI 助理面板。
// 掛在 AuthGuard 內,跨頁保留對話;提問時自動附上目前所在頁面當作上下文。

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { askStream, turnsToHistory } from "./chat";
import { WidgetGrid, type Widget } from "./widget";

type Source = { tool: string; label?: string; table_code?: string; by?: string };
type Usage = { cost_usd: number; model: string; input_tokens?: number; output_tokens?: number };
type Answer = { answer: string; widgets: Widget[]; sources: Source[]; usage?: Usage };
type Turn = { q: string; pending?: boolean; status?: string } & Partial<Answer> & { error?: string };

function sourceText(sources: Source[]): string {
  return Array.from(new Set(sources.map((s) => s.label ?? s.table_code ?? s.tool))).join("、");
}

const PAGE_LABELS: Record<string, string> = {
  "/": "首頁(經營總覽儀表板)",
  "/dashboard": "經營儀表板",
  "/assistant": "AI 助理",
  "/data": "資料檢視(ERP 查詢)",
  "/billing": "電費作業",
  "/audit": "稽核紀錄",
};

const EXAMPLES = [
  "各社區這個月應收總額,畫個圖",
  "2026 每月平均電費的折線圖",
  "幫我做這個月的經營儀表板",
];

function pageLabel(pathname: string): string {
  if (PAGE_LABELS[pathname]) return PAGE_LABELS[pathname];
  const hit = Object.entries(PAGE_LABELS).find(([p]) => p !== "/" && pathname.startsWith(p));
  return hit ? hit[1] : pathname;
}

export function GeniePanel() {
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false); // 寬版:看多欄表格/大圖時展開
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const pathname = usePathname();
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const context = pageLabel(pathname ?? "/");
  const totalCost = turns.reduce((s, t) => s + (t.usage?.cost_usd ?? 0), 0);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, loading]);

  async function send(question: string) {
    const text = question.trim();
    if (!text || loading) return;
    setQ("");
    setLoading(true);
    setTurns((t) => [...t, { q: text, pending: true }]);
    try {
      const res = await askStream<Answer>(
        { question: text, context, history: turnsToHistory(turns) },
        (label) => setTurns((t) => [...t.slice(0, -1), { q: text, pending: true, status: label }]),
      );
      setTurns((t) => [...t.slice(0, -1), { q: text, ...res }]);
    } catch (err) {
      setTurns((t) => [
        ...t.slice(0, -1),
        { q: text, error: err instanceof Error ? err.message : "查詢失敗" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {!open ? (
        <button className="genie-tab" type="button" onClick={() => setOpen(true)} aria-label="開啟 AI 助理">
          ✦ AI 助理
        </button>
      ) : null}

      <aside
        className={`genie-panel${open ? " genie-panel-open" : ""}${wide ? " genie-panel-wide" : ""}`}
        aria-hidden={!open}
      >
        <header className="genie-header">
          <span className="genie-header-title">✦ Genie 資料助理</span>
          <span className="genie-context" title={`目前頁面:${context}`}>{context}</span>
          {totalCost > 0 ? (
            <span className="genie-context" title="本次開啟以來的 API 花費(美金)">
              ${totalCost.toFixed(3)}
            </span>
          ) : null}
          <button
            className="genie-close"
            type="button"
            onClick={() => setWide((w) => !w)}
            aria-label={wide ? "縮回窄版" : "展開寬版"}
            title={wide ? "縮回窄版" : "展開寬版(看多欄表格更舒服)"}
          >
            {wide ? "⇥" : "⇤"}
          </button>
          <button className="genie-close" type="button" onClick={() => setOpen(false)} aria-label="收合">
            ✕
          </button>
        </header>

        <div className="genie-body" ref={bodyRef}>
          {turns.length === 0 ? (
            <div className="genie-examples">
              <span className="muted" style={{ fontSize: 12.5 }}>
                用一句話問資料庫,例如:
              </span>
              {EXAMPLES.map((e) => (
                <button key={e} className="genie-example" type="button" onClick={() => send(e)}>
                  {e}
                </button>
              ))}
            </div>
          ) : null}

          {turns.map((t, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="genie-turn-q">{t.q}</div>
              {t.pending ? (
                <div className="genie-thinking">{t.status ?? "查詢資料庫中"}…</div>
              ) : t.error ? (
                <div className="error" style={{ margin: 0 }}>⚠️ {t.error}</div>
              ) : (
                <div className="genie-turn-a">
                  <span>{t.answer}</span>
                  {t.widgets?.length ? <WidgetGrid widgets={t.widgets} /> : null}
                  {t.sources?.length || t.usage ? (
                    <div className="genie-sources">
                      {t.sources?.length ? <>▸ 來源:{sourceText(t.sources)}</> : null}
                      {t.usage ? (
                        <span style={{ float: "right" }}>${t.usage.cost_usd.toFixed(4)}</span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="genie-input-row">
          <input
            ref={inputRef}
            className="filter-input"
            value={q}
            placeholder={`針對「${context}」或任何資料提問…`}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return; // 注音/倉頡選字的 Enter 不是送出
              if (e.key === "Enter") send(q);
            }}
          />
          <button className="button button-primary" type="button" onClick={() => send(q)} disabled={loading}>
            {loading ? "…" : "問"}
          </button>
        </div>
      </aside>
    </>
  );
}
