"use client";

import { ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson, filenameFromContentDisposition } from "../lib/api";

type TableMeta = {
  code: string;
  label: string;
};

type ColumnMeta = {
  code: string;
  label: string;
  type: "text" | "enum" | "date" | "ym" | "number" | string;
  filterable: boolean;
  operators: string[];
  exportable: boolean;
};

type FilterItem = {
  col: string;
  op: string;
  val: unknown;
};

type SortItem = {
  col: string;
  dir: "asc" | "desc";
};

type QueryResponse = {
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  size: number;
};

type FilterDraft = {
  op: string;
  value: string;
  from: string;
  to: string;
  checked: boolean;
};

const PAGE_SIZE = 50;

function defaultOperator(column: ColumnMeta) {
  if (column.operators.includes("contains")) {
    return "contains";
  }
  if (column.operators.includes("range")) {
    return "range";
  }
  if (column.operators.includes("eq")) {
    return "eq";
  }
  return column.operators[0] ?? "eq";
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "－";
  }
  return String(value);
}

function buildFilters(columns: ColumnMeta[], drafts: Record<string, FilterDraft>): FilterItem[] {
  return columns.flatMap<FilterItem>((column) => {
    if (!column.filterable) {
      return [];
    }
    const draft = drafts[column.code];
    if (!draft) {
      return [];
    }
    if (draft.op === "isnull") {
      return [{ col: column.code, op: "isnull", val: draft.checked }];
    }
    if (draft.op === "range") {
      const from = draft.from.trim();
      const to = draft.to.trim();
      if (!from && !to) {
        return [];
      }
      const normalize = (value: string) => {
        if (!value) {
          return null;
        }
        return column.type === "number" ? Number(value) : value;
      };
      return [{ col: column.code, op: "range", val: [normalize(from), normalize(to)] }];
    }
    const value = draft.value.trim();
    if (!value) {
      return [];
    }
    if (draft.op === "in") {
      return [
        {
          col: column.code,
          op: "in",
          val: value
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        },
      ];
    }
    return [
      { col: column.code, op: draft.op, val: column.type === "number" ? Number(value) : value },
    ];
  });
}

function SortMarker({ sort, code }: { sort: SortItem[]; code: string }) {
  const active = sort[0]?.col === code ? sort[0] : null;
  if (!active) {
    return <span className="muted">↕</span>;
  }
  return <span>{active.dir === "asc" ? "↑" : "↓"}</span>;
}

function FilterControl({
  column,
  draft,
  onChange,
}: {
  column: ColumnMeta;
  draft: FilterDraft;
  onChange: (draft: FilterDraft) => void;
}) {
  const operators = column.operators.length ? column.operators : [defaultOperator(column)];
  const setOperator = (op: string) => onChange({ ...draft, op });

  return (
    <div className="filter-card">
      <div className="filter-label">{column.label}</div>
      <div className="filter-row">
        {operators.length > 1 ? (
          <select
            className="filter-select"
            value={draft.op}
            onChange={(event) => setOperator(event.target.value)}
          >
            {operators.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
        ) : null}
        {draft.op === "isnull" ? (
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={draft.checked}
              onChange={(event) => onChange({ ...draft, checked: event.target.checked })}
            />
            空值
          </label>
        ) : draft.op === "range" ? (
          <>
            <input
              className="filter-input"
              type={column.type === "number" ? "number" : column.type === "date" ? "date" : "text"}
              placeholder="起"
              value={draft.from}
              onChange={(event) => onChange({ ...draft, from: event.target.value })}
            />
            <input
              className="filter-input"
              type={column.type === "number" ? "number" : column.type === "date" ? "date" : "text"}
              placeholder="迄"
              value={draft.to}
              onChange={(event) => onChange({ ...draft, to: event.target.value })}
            />
          </>
        ) : column.type === "enum" && draft.op !== "contains" ? (
          <input
            className="filter-input"
            placeholder={draft.op === "in" ? "逗號分隔" : "輸入值"}
            value={draft.value}
            onChange={(event) => onChange({ ...draft, value: event.target.value })}
          />
        ) : (
          <input
            className="filter-input"
            type={column.type === "number" ? "number" : "text"}
            placeholder={draft.op === "contains" ? "包含" : "等於"}
            value={draft.value}
            onChange={(event) => onChange({ ...draft, value: event.target.value })}
          />
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [columns, setColumns] = useState<ColumnMeta[]>([]);
  const [drafts, setDrafts] = useState<Record<string, FilterDraft>>({});
  const [filters, setFilters] = useState<FilterItem[]>([]);
  const [sort, setSort] = useState<SortItem[]>([]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<QueryResponse>({ rows: [], total: 0, page: 1, size: PAGE_SIZE });
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<TableMeta[]>("/api/meta/tables")
      .then((items) => {
        setTables(items);
        setSelectedTable(items[0]?.code ?? "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "表清單載入失敗"));
  }, []);

  useEffect(() => {
    if (!selectedTable) {
      setColumns([]);
      return;
    }
    setError("");
    setPage(1);
    setSort([]);
    apiJson<ColumnMeta[]>(`/api/meta/tables/${selectedTable}/columns`)
      .then((items) => {
        setColumns(items);
        const nextDrafts = Object.fromEntries(
          items
            .filter((column) => column.filterable)
            .map((column) => [
              column.code,
              { op: defaultOperator(column), value: "", from: "", to: "", checked: true },
            ]),
        ) as Record<string, FilterDraft>;
        setDrafts(nextDrafts);
        setFilters([]);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "欄位載入失敗"));
  }, [selectedTable]);

  const loadData = useCallback(async () => {
    if (!selectedTable || !columns.length) {
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const response = await apiJson<QueryResponse>(`/api/data/${selectedTable}/query`, {
        method: "POST",
        body: JSON.stringify({ filters, sort, page, size: PAGE_SIZE }),
      });
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "資料載入失敗");
    } finally {
      setIsLoading(false);
    }
  }, [columns.length, filters, page, selectedTable, sort]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tableColumns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      columns.map((column) => ({
        accessorKey: column.code,
        header: column.label,
        cell: (info) => formatCell(info.getValue()),
      })),
    [columns],
  );

  const table = useReactTable({
    data: data.rows,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
  });

  const maxPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const selectedTableLabel =
    tables.find((item) => item.code === selectedTable)?.label ?? selectedTable;

  function applyFilters() {
    setPage(1);
    setFilters(buildFilters(columns, drafts));
  }

  function clearFilters() {
    const nextDrafts = Object.fromEntries(
      columns
        .filter((column) => column.filterable)
        .map((column) => [
          column.code,
          { op: defaultOperator(column), value: "", from: "", to: "", checked: true },
        ]),
    ) as Record<string, FilterDraft>;
    setDrafts(nextDrafts);
    setFilters([]);
    setPage(1);
  }

  function toggleSort(code: string) {
    setPage(1);
    setSort((current) => {
      const active = current[0];
      if (active?.col !== code) {
        return [{ col: code, dir: "asc" }];
      }
      if (active.dir === "asc") {
        return [{ col: code, dir: "desc" }];
      }
      return [];
    });
  }

  async function exportData() {
    if (!selectedTable) {
      return;
    }
    setIsExporting(true);
    setError("");
    try {
      const response = await apiFetch(`/api/data/${selectedTable}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters, sort }),
      });
      if (!response.ok) {
        const message = await response
          .json()
          .then((body) => body.detail ?? "匯出失敗")
          .catch(() => "匯出失敗");
        throw new Error(String(message));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filenameFromContentDisposition(
        response.headers.get("Content-Disposition"),
        `${selectedTable}.xlsx`,
      );
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "匯出失敗");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <div className="toolbar">
          <div className="toolbar-main">
            <div className="field">
              <label htmlFor="table-code">表</label>
              <select
                id="table-code"
                className="control"
                value={selectedTable}
                onChange={(event) => setSelectedTable(event.target.value)}
              >
                {tables.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              className="button button-primary"
              type="button"
              onClick={applyFilters}
              disabled={!selectedTable}
            >
              查詢
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={clearFilters}
              disabled={!selectedTable}
            >
              清除
            </button>
          </div>
          <button
            className="button button-secondary"
            type="button"
            onClick={exportData}
            disabled={!selectedTable || isExporting}
          >
            {isExporting ? "匯出中" : "匯出"}
          </button>
        </div>
        <div className="filters">
          {columns.filter((column) => column.filterable).length ? (
            columns
              .filter((column) => column.filterable)
              .map((column) => (
                <FilterControl
                  key={column.code}
                  column={column}
                  draft={
                    drafts[column.code] ?? {
                      op: defaultOperator(column),
                      value: "",
                      from: "",
                      to: "",
                      checked: true,
                    }
                  }
                  onChange={(draft) =>
                    setDrafts((current) => ({ ...current, [column.code]: draft }))
                  }
                />
              ))
          ) : (
            <div className="muted">此表無可篩選欄位</div>
          )}
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="card table-card">
        <div className="pagination">
          <div>
            <strong>{selectedTableLabel}</strong>
            <span className="muted">　共 {data.total.toLocaleString()} 筆</span>
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
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id}>
                      <button
                        className="sort-button"
                        type="button"
                        onClick={() => toggleSort(header.column.id)}
                        title="排序"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <SortMarker sort={sort} code={header.column.id} />
                      </button>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!data.rows.length ? (
            <div className="empty-state">{isLoading ? "載入資料中" : "無資料"}</div>
          ) : null}
        </div>
        <div className="pagination">
          <span className="muted">
            第 {page} / {maxPage} 頁，每頁 {PAGE_SIZE} 筆
          </span>
          <span className="muted">{isLoading ? "更新中" : null}</span>
        </div>
      </section>
    </main>
  );
}
