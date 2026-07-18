"use client";

import { useState } from "react";
import Link from "next/link";
import { apiJson } from "../../lib/api";
import { WidgetGrid, type Widget } from "../_components/widget";

type Source = { tool: string; label?: string; table_code?: string };
type Answer = {
  answer: string;
  widgets: Widget[];
  sources: Source[];
  usage?: { cost_usd: number; model: string };
};
type Turn = { q: string } & Partial<Answer> & { error?: string };

const EXAMPLES = [
  "各社區這個月應收總額,畫個圖",
  "幫我做這個月的經營儀表板",
  "資料庫最新的帳務月份是哪一個月?",
];

export default function AssistantPage() {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);

  async function send(question: string) {
    const text = question.trim();
    if (!text || loading) return;
    setQ("");
    setLoading(true);
    setTurns((t) => [...t, { q: text }]);
    try {
      const res = await apiJson<Answer>("/api/assistant/ask", {
        method: "POST",
        body: JSON.stringify({ question: text }),
      });
      setTurns((t) => [...t.slice(0, -1), { q: text, ...res }]);
    } catch (err) {
      setTurns((t) => [...t.slice(0, -1), { q: text, error: err instanceof Error ? err.message : "查詢失敗" }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>資料客服助理</h2>
        <Link href="/dashboard" className="button button-secondary">經營儀表板</Link>
      </div>

      {turns.length === 0 ? (
        <div className="card">
          <div className="muted" style={{ marginBottom: 8 }}>試試這些問題:</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {EXAMPLES.map((e) => (
              <button key={e} className="button button-secondary" onClick={() => send(e)}>{e}</button>
            ))}
          </div>
        </div>
      ) : null}

      <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
        {turns.map((t, i) => (
          <div key={i} className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>🙋 {t.q}</div>
            {t.error ? (
              <div className="error">⚠️ {t.error}</div>
            ) : (
              <>
                <div style={{ whiteSpace: "pre-wrap", marginBottom: t.widgets?.length ? 12 : 0 }}>
                  🤖 {t.answer}
                </div>
                {t.widgets?.length ? <WidgetGrid widgets={t.widgets} /> : null}
                {t.sources?.length || t.usage ? (
                  <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                    {t.sources?.length ? (
                      <>▸ 來源:{Array.from(new Set(t.sources.map((s) => s.label ?? s.table_code ?? s.tool))).join("、")}</>
                    ) : null}
                    {t.usage ? <span style={{ float: "right" }}>${t.usage.cost_usd.toFixed(4)}</span> : null}
                  </div>
                ) : null}
              </>
            )}
          </div>
        ))}
        {loading ? <div className="muted">查詢中…</div> : null}
      </div>

      <div className="toolbar" style={{ marginTop: 12, position: "sticky", bottom: 0, background: "#fff", padding: "8px 0" }}>
        <input
          className="filter-input"
          style={{ flex: 1 }}
          value={q}
          placeholder="例:王小姐這個月帳單多少?"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(q)}
        />
        <button className="button button-primary" onClick={() => send(q)} disabled={loading}>
          {loading ? "查詢中" : "問"}
        </button>
      </div>
    </main>
  );
}
