"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../lib/api";
import { useAuth } from "../providers";

type AuditActor = {
  id?: number;
  username?: string;
};

type AuditRow = {
  id?: number;
  ts?: string;
  created_at?: string;
  actor?: number | string | AuditActor | null;
  actor_username?: string | null;
  action: string;
  table_code?: string | null;
  row_count?: number | null;
  filters?: unknown;
};

type AuditResponse = {
  rows?: AuditRow[];
  items?: AuditRow[];
  total?: number;
  page?: number;
  size?: number;
};

type AppliedFilters = {
  action: string;
  from: string;
  to: string;
};

const ACTION_OPTIONS = ["login", "query", "export", "audit_query", "logout", "metadata_change"];
const PAGE_SIZES = [25, 50, 100];

function formatTime(value?: string) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatActor(row: AuditRow) {
  if (row.actor_username) {
    return row.actor_username;
  }
  if (typeof row.actor === "object" && row.actor) {
    return row.actor.username ?? (row.actor.id ? String(row.actor.id) : "-");
  }
  if (row.actor === null || row.actor === undefined || row.actor === "") {
    return "-";
  }
  return String(row.actor);
}

function formatFilters(value: unknown) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string") {
    return value || "-";
  }
  if (Array.isArray(value) && value.length === 0) {
    return "-";
  }
  if (typeof value === "object" && Object.keys(value).length === 0) {
    return "-";
  }
  return JSON.stringify(value);
}

function normalizeAuditResponse(response: AuditResponse | AuditRow[]): Required<
  Pick<AuditResponse, "total">
> & {
  rows: AuditRow[];
} {
  if (Array.isArray(response)) {
    return { rows: response, total: response.length };
  }
  const rows = response.rows ?? response.items ?? [];
  return { rows, total: response.total ?? rows.length };
}

export default function AuditPage() {
  const { user } = useAuth();
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const [appliedFilters, setAppliedFilters] = useState<AppliedFilters>({
    action: "",
    from: "",
    to: "",
  });
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const isAdmin = user?.role === "admin";

  const queryPath = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      size: String(size),
    });
    if (appliedFilters.action) {
      params.set("action", appliedFilters.action);
    }
    if (appliedFilters.from) {
      params.set("from", appliedFilters.from);
    }
    if (appliedFilters.to) {
      params.set("to", appliedFilters.to);
    }
    return `/api/audit?${params.toString()}`;
  }, [appliedFilters, page, size]);

  const loadAudit = useCallback(async () => {
    if (!isAdmin) {
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const response = await apiJson<AuditResponse | AuditRow[]>(queryPath);
      const normalized = normalizeAuditResponse(response);
      setRows(normalized.rows);
      setTotal(normalized.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "稽核紀錄載入失敗");
    } finally {
      setIsLoading(false);
    }
  }, [isAdmin, queryPath]);

  useEffect(() => {
    loadAudit();
  }, [loadAudit]);

  const maxPage = Math.max(1, Math.ceil(total / size));

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({ action, from, to });
  }

  function clearFilters() {
    setAction("");
    setFrom("");
    setTo("");
    setPage(1);
    setAppliedFilters({ action: "", from: "", to: "" });
  }

  function changeSize(nextSize: number) {
    setPage(1);
    setSize(nextSize);
  }

  if (!isAdmin) {
    return (
      <main className="page">
        <section className="card notice-card">
          <h1 className="section-title">無權限</h1>
          <p className="muted">此頁僅限管理員檢視。</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <section className="card">
        <form className="toolbar" onSubmit={applyFilters}>
          <div className="toolbar-main">
            <div className="field">
              <label htmlFor="audit-action">動作</label>
              <select
                id="audit-action"
                className="control"
                value={action}
                onChange={(event) => setAction(event.target.value)}
              >
                <option value="">全部</option>
                {ACTION_OPTIONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="audit-from">起始日期</label>
              <input
                id="audit-from"
                className="control"
                type="date"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="audit-to">結束日期</label>
              <input
                id="audit-to"
                className="control"
                type="date"
                value={to}
                onChange={(event) => setTo(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="audit-size">每頁筆數</label>
              <select
                id="audit-size"
                className="control"
                value={size}
                onChange={(event) => changeSize(Number(event.target.value))}
              >
                {PAGE_SIZES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <button className="button button-primary" type="submit" disabled={isLoading}>
              查詢
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={clearFilters}
              disabled={isLoading}
            >
              清除
            </button>
          </div>
        </form>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="card table-card">
        <div className="pagination">
          <div>
            <strong>稽核紀錄</strong>
            <span className="muted"> 共 {total.toLocaleString()} 筆</span>
          </div>
          <div className="page-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || isLoading}
            >
              上一頁
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => setPage((current) => Math.min(maxPage, current + 1))}
              disabled={page >= maxPage || isLoading}
            >
              下一頁
            </button>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>時間</th>
                <th>使用者(actor)</th>
                <th>動作(action)</th>
                <th>表(table_code)</th>
                <th>筆數(row_count)</th>
                <th>篩選(filters summary)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.id ?? `${row.ts ?? row.created_at ?? "audit"}-${index}`}>
                  <td>{formatTime(row.ts ?? row.created_at)}</td>
                  <td>{formatActor(row)}</td>
                  <td>{row.action}</td>
                  <td>{row.table_code ?? "-"}</td>
                  <td>{row.row_count ?? "-"}</td>
                  <td className="filters-summary">{formatFilters(row.filters)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length ? (
            <div className="empty-state">{isLoading ? "載入稽核紀錄中" : "目前沒有稽核紀錄"}</div>
          ) : null}
        </div>
        <div className="pagination">
          <span className="muted">
            第 {page} / {maxPage} 頁，每頁 {size} 筆
          </span>
          <span className="muted">{isLoading ? "更新中" : null}</span>
        </div>
      </section>
    </main>
  );
}
