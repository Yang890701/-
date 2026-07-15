"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../../lib/api";

export type MasterTableCode = "site" | "meter" | "room";

export type MasterField = {
  key: string;
  label: string;
  type?: "text" | "number";
  required?: boolean;
  placeholder?: string;
};

export type MasterPageConfig = {
  tableCode: MasterTableCode;
  title: string;
  description: string;
  fields: readonly MasterField[];
};

type MasterValue = string | number | null;

type MasterRow = {
  id: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
} & Record<string, MasterValue>;

type MasterListResponse = {
  rows: MasterRow[];
  total: number;
};

type FormMode = "create" | "edit";
type FormState = Record<string, string>;

function makeEmptyForm(fields: readonly MasterField[]): FormState {
  return Object.fromEntries(fields.map((field) => [field.key, ""]));
}

function rowToForm(fields: readonly MasterField[], row: MasterRow): FormState {
  return Object.fromEntries(
    fields.map((field) => {
      const value = row[field.key];
      return [field.key, value === null || value === undefined ? "" : String(value)];
    }),
  );
}

function formatValue(value: MasterValue | undefined) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
}

function buildPayload(fields: readonly MasterField[], formState: FormState) {
  return Object.fromEntries(
    fields.map((field) => {
      const rawValue = formState[field.key]?.trim() ?? "";
      if (!rawValue) {
        if (field.required) {
          throw new Error(`${field.label}為必填`);
        }
        return [field.key, null];
      }
      if (field.type === "number") {
        const parsed = Number(rawValue);
        if (!Number.isFinite(parsed)) {
          throw new Error(`${field.label}必須是數字`);
        }
        return [field.key, parsed];
      }
      return [field.key, rawValue];
    }),
  );
}

export function MasterPage({ config }: { config: MasterPageConfig }) {
  const [rows, setRows] = useState<MasterRow[]>([]);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [formMode, setFormMode] = useState<FormMode | null>(null);
  const [editingRowId, setEditingRowId] = useState<number | null>(null);
  const [formState, setFormState] = useState<FormState>(() => makeEmptyForm(config.fields));
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const endpoint = `/api/master/${config.tableCode}`;
  const activeRows = useMemo(() => rows.filter((row) => !row.deleted_at).length, [rows]);

  const loadRows = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const query = includeInactive ? "?include_inactive=true" : "";
      const response = await apiJson<MasterListResponse>(`${endpoint}${query}`);
      setRows(response.rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "讀取資料失敗");
    } finally {
      setIsLoading(false);
    }
  }, [endpoint, includeInactive]);

  useEffect(() => {
    loadRows();
  }, [loadRows]);

  function startCreate() {
    setFormMode("create");
    setEditingRowId(null);
    setFormState(makeEmptyForm(config.fields));
    setError("");
  }

  function startEdit(row: MasterRow) {
    setFormMode("edit");
    setEditingRowId(row.id);
    setFormState(rowToForm(config.fields, row));
    setError("");
  }

  function closeForm() {
    setFormMode(null);
    setEditingRowId(null);
    setFormState(makeEmptyForm(config.fields));
  }

  async function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!formMode) {
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      const payload = buildPayload(config.fields, formState);
      const path = formMode === "edit" ? `${endpoint}/${editingRowId}` : endpoint;
      await apiJson<MasterRow>(path, {
        method: formMode === "edit" ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      closeForm();
      await loadRows();
    } catch (err) {
      setError(err instanceof Error ? err.message : "儲存失敗");
    } finally {
      setIsSaving(false);
    }
  }

  async function stopRow(row: MasterRow) {
    if (!window.confirm(`確定停用 ${row.id}？`)) {
      return;
    }
    setError("");
    try {
      await apiJson<MasterRow>(`${endpoint}/${row.id}`, { method: "DELETE" });
      await loadRows();
    } catch (err) {
      setError(err instanceof Error ? err.message : "停用失敗");
    }
  }

  return (
    <main className="page">
      <section className="card master-header">
        <div>
          <p className="portal-kicker">主檔管理</p>
          <h1 className="section-title">{config.title}</h1>
          <p className="muted">{config.description}</p>
        </div>
        <div className="master-header-actions">
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
            />
            顯示已停用
          </label>
          <button className="button button-primary" type="button" onClick={startCreate}>
            新增
          </button>
        </div>
      </section>

      {formMode ? (
        <section className="card master-form-card">
          <form className="master-form" onSubmit={submitForm}>
            <div className="master-form-heading">
              <strong>{formMode === "edit" ? "編輯" : "新增"}</strong>
              <span className="muted">{config.title}</span>
            </div>
            <div className="master-form-grid">
              {config.fields.map((field) => (
                <label className="field" key={field.key}>
                  <span>
                    {field.label}
                    {field.required ? <span className="required-mark"> *</span> : null}
                  </span>
                  <input
                    className="control"
                    type={field.type === "number" ? "number" : "text"}
                    required={field.required}
                    placeholder={field.placeholder}
                    value={formState[field.key] ?? ""}
                    onChange={(event) =>
                      setFormState((current) => ({
                        ...current,
                        [field.key]: event.target.value,
                      }))
                    }
                  />
                </label>
              ))}
            </div>
            <div className="master-form-actions">
              <button className="button button-primary" type="submit" disabled={isSaving}>
                {isSaving ? "儲存中" : "儲存"}
              </button>
              <button className="button button-secondary" type="button" onClick={closeForm}>
                取消
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {error ? <div className="error">{error}</div> : null}

      <section className="card table-card">
        <div className="pagination">
          <div>
            <strong>{config.title}</strong>
            <span className="muted">
              {" "}
              使用中 {activeRows.toLocaleString()} 筆 / 目前顯示 {rows.length.toLocaleString()} 筆
            </span>
          </div>
          <span className="muted">{isLoading ? "讀取中" : null}</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                {config.fields.map((field) => (
                  <th key={field.key}>{field.label}</th>
                ))}
                <th>狀態</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const inactive = Boolean(row.deleted_at);
                return (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    {config.fields.map((field) => (
                      <td key={field.key}>{formatValue(row[field.key])}</td>
                    ))}
                    <td>
                      <span className={`status-pill ${inactive ? "status-pill-inactive" : ""}`}>
                        {inactive ? "已停用" : "使用中"}
                      </span>
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="button button-secondary button-small"
                          type="button"
                          onClick={() => startEdit(row)}
                          disabled={inactive}
                        >
                          編輯
                        </button>
                        <button
                          className="button button-secondary button-small"
                          type="button"
                          onClick={() => stopRow(row)}
                          disabled={inactive}
                        >
                          停用
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!rows.length ? (
            <div className="empty-state">{isLoading ? "讀取資料中" : "尚無資料"}</div>
          ) : null}
        </div>
      </section>
    </main>
  );
}
