"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiJson } from "../../lib/api";
import { WidgetGrid, type Widget } from "../_components/widget";

type Dashboard = { title: string; widgets: Widget[]; note?: string };

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiJson<Dashboard>("/api/assistant/dashboard"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>{data?.title ?? "經營儀表板"}</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="button button-secondary" onClick={load} disabled={loading}>
            {loading ? "更新中" : "重新整理"}
          </button>
          <Link href="/assistant" className="button button-primary">問 AI</Link>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}
      {data?.note ? <div className="muted">{data.note}</div> : null}
      {data?.widgets?.length ? <WidgetGrid widgets={data.widgets} /> : (!loading && !error ? <div className="muted">尚無資料</div> : null)}
    </main>
  );
}
