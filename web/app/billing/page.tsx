"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson } from "../../lib/api";

type BillingStatus = "draft" | "calculated" | "approved" | "published" | "reversed";
type BillingAction = "approve" | "publish" | "reverse";
type ScopeMode = "all" | "site" | "room";

type BillingScope =
  | { type: "all" }
  | { site_id: number }
  | { room_id: number }
  | { site_ids: number[] }
  | { room_ids: number[] };

type SiteSummary = {
  site_id: number;
  total_amount: number;
  calculated: number;
  skipped: number;
};

type BillingSummary = {
  total_rooms: number;
  calculated: number;
  skipped: number;
  total_amount: number;
  by_site?: SiteSummary[];
};

type BillingRunResponse = {
  run_id: number;
  billing_ym?: string;
  scope?: BillingScope;
  version?: number;
  status: BillingStatus;
  summary: BillingSummary;
};

type BillingChargeLine = {
  id: number;
  charge_type: string;
  amount: number;
  source_ref?: unknown;
};

type BillingDetailRow = {
  detail_id: number;
  room_id: number;
  room_code: string | null;
  subtotal: number | null;
  status: string | null;
  reason?: string | null;
  charge_lines: BillingChargeLine[];
};

type BillingDetailsResponse = {
  rows: BillingDetailRow[];
  total: number;
  page: number;
  size: number;
};

const YM_PATTERN = /^[0-9]{6}$/;
const PAGE_SIZES = [25, 50, 100, 200];

const STATUS_LABELS: Record<BillingStatus, string> = {
  draft: "草稿",
  calculated: "已試算",
  approved: "已核准",
  published: "已發布",
  reversed: "已沖銷",
};

const ACTION_LABELS: Record<BillingAction, string> = {
  approve: "核准",
  publish: "發布",
  reverse: "沖銷",
};

function statusPillClass(status: BillingStatus) {
  if (status === "published") {
    return "status-pill";
  }
  if (status === "approved") {
    return "status-pill status-pill-warning";
  }
  if (status === "reversed") {
    return "status-pill status-pill-inactive";
  }
  return "status-pill status-pill-neutral";
}

function detailStatusPillClass(status: string | null) {
  if (status === "calculated") {
    return "status-pill";
  }
  if (status === "skipped") {
    return "status-pill status-pill-warning";
  }
  return "status-pill status-pill-neutral";
}

function formatDetailStatus(status: string | null) {
  if (!status) {
    return "-";
  }
  if (status === "calculated") {
    return "已試算";
  }
  if (status === "skipped") {
    return "略過";
  }
  return status;
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `NT$ ${value.toLocaleString("zh-TW")}`;
}

function formatBillingYm(value: string | undefined) {
  if (!value || value.length !== 6) {
    return value ?? "-";
  }
  return `${value.slice(0, 4)}/${value.slice(4, 6)}`;
}

function validateBillingYm(value: string) {
  const trimmed = value.trim();
  if (!YM_PATTERN.test(trimmed)) {
    throw new Error("帳單年月必須為 YYYYMM，例如 202607");
  }
  const month = Number(trimmed.slice(4, 6));
  if (month < 1 || month > 12) {
    throw new Error("帳單年月月份必須介於 01 到 12");
  }
  return trimmed;
}

function positiveInteger(value: string, label: string) {
  const parsed = Number(value.trim());
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${label}必須是正整數`);
  }
  return parsed;
}

function buildScope(mode: ScopeMode, siteId: string, roomId: string): BillingScope {
  if (mode === "all") {
    return { type: "all" };
  }
  if (mode === "site") {
    return { site_id: positiveInteger(siteId, "案場 ID") };
  }
  return { room_id: positiveInteger(roomId, "房號 ID") };
}

function formatScope(scope: BillingScope | undefined) {
  if (!scope) {
    return "-";
  }
  if ("type" in scope && scope.type === "all") {
    return "全部";
  }
  if ("site_id" in scope) {
    return `指定案場 #${scope.site_id}`;
  }
  if ("room_id" in scope) {
    return `指定房號 #${scope.room_id}`;
  }
  if ("site_ids" in scope) {
    return `指定案場 #${scope.site_ids.join(", #")}`;
  }
  if ("room_ids" in scope) {
    return `指定房號 #${scope.room_ids.join(", #")}`;
  }
  return "全部";
}

function extractReason(row: BillingDetailRow) {
  if (row.reason) {
    return row.reason;
  }
  if (row.status === "skipped") {
    return "後端未提供原因";
  }
  return "-";
}

async function mutationJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw new Error(await billingErrorMessage(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function billingErrorMessage(response: Response) {
  const detail = await response
    .json()
    .then((body: { detail?: unknown }) =>
      typeof body.detail === "string" ? body.detail : "API request failed",
    )
    .catch(() => "API request failed");
  const lowerDetail = detail.toLowerCase();

  if (response.status === 403) {
    return "權限不足: 您沒有執行此電費作業的權限。";
  }
  if (response.status === 409) {
    if (lowerDetail.includes("already published")) {
      return `重複發布: ${detail}`;
    }
    if (lowerDetail.includes("already exists") || lowerDetail.includes("duplicate")) {
      return `重複建立: ${detail}`;
    }
    if (lowerDetail.includes("must be")) {
      return `狀態不符: ${detail}`;
    }
    return `狀態衝突: ${detail}`;
  }
  if (response.status === 400) {
    return `資料格式錯誤: ${detail}`;
  }
  return detail;
}

function readableError(err: unknown, fallback: string) {
  if (!(err instanceof Error)) {
    return fallback;
  }
  if (err.message === "Forbidden") {
    return "權限不足: 您沒有檢視或操作此電費作業的權限。";
  }
  return err.message || fallback;
}

function canRunAction(status: BillingStatus, action: BillingAction) {
  if (action === "approve") {
    return status === "draft" || status === "calculated";
  }
  if (action === "publish") {
    return status === "approved";
  }
  return status === "published";
}

function electricityLine(row: BillingDetailRow) {
  return row.charge_lines.find((line) => line.charge_type === "電費") ?? row.charge_lines[0];
}

export default function BillingPage() {
  const [billingYm, setBillingYm] = useState("");
  const [scopeMode, setScopeMode] = useState<ScopeMode>("all");
  const [siteId, setSiteId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [run, setRun] = useState<BillingRunResponse | null>(null);
  const [details, setDetails] = useState<BillingDetailsResponse>({
    rows: [],
    total: 0,
    page: 1,
    size: 50,
  });
  const [detailsPage, setDetailsPage] = useState(1);
  const [detailsSize, setDetailsSize] = useState(50);
  const [isCreating, setIsCreating] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [actionInFlight, setActionInFlight] = useState<BillingAction | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const activeRunId = run?.run_id ?? null;
  const runPeriod = run?.billing_ym ?? billingYm.trim();
  const maxDetailsPage = Math.max(1, Math.ceil(details.total / detailsSize));

  const actionState = useMemo(
    () => ({
      approve: run ? canRunAction(run.status, "approve") : false,
      publish: run ? canRunAction(run.status, "publish") : false,
      reverse: run ? canRunAction(run.status, "reverse") : false,
    }),
    [run],
  );

  const loadDetails = useCallback(async (runId: number, page: number, size: number) => {
    setDetailsLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), size: String(size) });
      const response = await apiJson<BillingDetailsResponse>(
        `/api/billing/runs/${runId}/details?${params.toString()}`,
      );
      setDetails(response);
    } catch (err) {
      setError(readableError(err, "讀取試算明細失敗"));
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  const refreshRun = useCallback(async (runId: number) => {
    setIsRefreshing(true);
    try {
      const response = await apiJson<BillingRunResponse>(`/api/billing/runs/${runId}`);
      setRun(response);
      return response;
    } catch (err) {
      setError(readableError(err, "更新批次狀態失敗"));
      return null;
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (activeRunId === null) {
      return;
    }
    void loadDetails(activeRunId, detailsPage, detailsSize);
  }, [activeRunId, detailsPage, detailsSize, loadDetails]);

  async function createRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsCreating(true);
    setError("");
    setMessage("");
    try {
      const response = await mutationJson<BillingRunResponse>("/api/billing/runs", {
        method: "POST",
        body: JSON.stringify({
          billing_ym: validateBillingYm(billingYm),
          scope: buildScope(scopeMode, siteId, roomId),
        }),
      });
      setRun(response);
      setDetailsPage(1);
      setMessage("試算已建立，請確認明細後核准。");
    } catch (err) {
      setError(readableError(err, "建立試算失敗"));
    } finally {
      setIsCreating(false);
    }
  }

  async function runAction(action: BillingAction) {
    if (!run || !canRunAction(run.status, action)) {
      return;
    }

    setActionInFlight(action);
    setError("");
    setMessage("");
    try {
      await mutationJson<BillingRunResponse>(`/api/billing/runs/${run.run_id}/${action}`, {
        method: "POST",
      });
      const refreshed = await refreshRun(run.run_id);
      await loadDetails(run.run_id, detailsPage, detailsSize);
      if (action === "approve") {
        setMessage("批次已核准，可以發布。");
      }
      if (action === "reverse") {
        setMessage("批次已沖銷。");
      }
      if (action === "publish" && refreshed?.billing_ym) {
        setBillingYm(refreshed.billing_ym);
      }
    } catch (err) {
      setError(readableError(err, `${ACTION_LABELS[action]}失敗`));
    } finally {
      setActionInFlight(null);
    }
  }

  function refreshCurrentRun() {
    if (activeRunId === null) {
      return;
    }
    setError("");
    setMessage("");
    void refreshRun(activeRunId).then(() => loadDetails(activeRunId, detailsPage, detailsSize));
  }

  function changeDetailsSize(nextSize: number) {
    setDetailsSize(nextSize);
    setDetailsPage(1);
  }

  return (
    <main className="page">
      <section className="card master-header">
        <div>
          <p className="portal-kicker">電費作業</p>
          <h1 className="section-title">繳租確認</h1>
          <p className="muted">建立電費試算，依狀態核准、發布並產生繳租確認明細。</p>
        </div>
        <div className="master-header-actions">
          <button
            className="button button-secondary"
            type="button"
            onClick={refreshCurrentRun}
            disabled={activeRunId === null || isRefreshing || detailsLoading}
          >
            {isRefreshing ? "更新中" : "重新整理"}
          </button>
        </div>
      </section>

      <section className="card master-form-card">
        <form className="master-form" onSubmit={createRun}>
          <div className="master-form-heading">
            <strong>建立試算</strong>
            <span className="muted">帳單年月與範圍會鎖定本次計費批次。</span>
          </div>
          <div className="master-form-grid">
            <label className="field">
              <span>
                帳單年月 <span className="required-mark">*</span>
              </span>
              <input
                className="control"
                inputMode="numeric"
                maxLength={6}
                pattern="[0-9]{6}"
                placeholder="202607"
                value={billingYm}
                onChange={(event) => setBillingYm(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>範圍</span>
              <select
                className="control"
                value={scopeMode}
                onChange={(event) => setScopeMode(event.target.value as ScopeMode)}
              >
                <option value="all">全部</option>
                <option value="site">指定案場</option>
                <option value="room">指定房號</option>
              </select>
            </label>
            {scopeMode === "site" ? (
              <label className="field">
                <span>
                  案場 ID <span className="required-mark">*</span>
                </span>
                <input
                  className="control"
                  inputMode="numeric"
                  value={siteId}
                  onChange={(event) => setSiteId(event.target.value)}
                  required
                />
              </label>
            ) : null}
            {scopeMode === "room" ? (
              <label className="field">
                <span>
                  房號 ID <span className="required-mark">*</span>
                </span>
                <input
                  className="control"
                  inputMode="numeric"
                  value={roomId}
                  onChange={(event) => setRoomId(event.target.value)}
                  required
                />
              </label>
            ) : null}
          </div>
          <div className="master-form-actions">
            <button className="button button-primary" type="submit" disabled={isCreating}>
              {isCreating ? "建立中" : "建立試算"}
            </button>
          </div>
        </form>
      </section>

      {error ? <div className="error">{error}</div> : null}
      {message ? <div className="message message-success">{message}</div> : null}

      {run ? (
        <>
          <section className="card master-form-card">
            <div className="billing-run-meta">
              <div>
                <strong>批次 #{run.run_id}</strong>
                <span className="muted">
                  {" "}
                  {formatBillingYm(runPeriod)} / {formatScope(run.scope)}
                  {run.version ? ` / v${run.version}` : ""}
                </span>
              </div>
              <span className={statusPillClass(run.status)}>{STATUS_LABELS[run.status]}</span>
            </div>
            <div className="billing-summary-grid">
              <div className="billing-stat">
                <span className="muted">總房數</span>
                <strong>{run.summary.total_rooms.toLocaleString()}</strong>
              </div>
              <div className="billing-stat">
                <span className="muted">已試算</span>
                <strong>{run.summary.calculated.toLocaleString()}</strong>
              </div>
              <div className="billing-stat">
                <span className="muted">略過</span>
                <strong>{run.summary.skipped.toLocaleString()}</strong>
              </div>
              <div className="billing-stat">
                <span className="muted">總金額</span>
                <strong>{formatMoney(run.summary.total_amount)}</strong>
              </div>
            </div>
            {run.summary.by_site?.length ? (
              <div className="table-scroll billing-summary-table">
                <table>
                  <thead>
                    <tr>
                      <th>案場</th>
                      <th>已試算</th>
                      <th>略過</th>
                      <th>小計</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.summary.by_site.map((site) => (
                      <tr key={site.site_id}>
                        <td>#{site.site_id}</td>
                        <td>{site.calculated.toLocaleString()}</td>
                        <td>{site.skipped.toLocaleString()}</td>
                        <td>{formatMoney(site.total_amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>

          <section className="card table-card">
            <div className="billing-action-bar">
              <div>
                <strong>狀態機</strong>
                <span className="muted"> 目前狀態 </span>
                <span className={statusPillClass(run.status)}>{STATUS_LABELS[run.status]}</span>
              </div>
              <div className="billing-action-buttons">
                {(Object.keys(ACTION_LABELS) as BillingAction[]).map((action) => (
                  <button
                    className={action === "approve" ? "button button-primary" : "button button-secondary"}
                    type="button"
                    key={action}
                    onClick={() => void runAction(action)}
                    disabled={!actionState[action] || actionInFlight !== null || isRefreshing}
                  >
                    {actionInFlight === action ? `${ACTION_LABELS[action]}中` : ACTION_LABELS[action]}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {run.status === "published" ? (
            <div className="message message-success">
              已發布：{formatBillingYm(runPeriod)} 的繳租確認明細已產生至 rent_confirm。
            </div>
          ) : null}

          <section className="card table-card">
            <div className="pagination">
              <div>
                <strong>試算明細</strong>
                <span className="muted">
                  {" "}
                  {detailsLoading ? "讀取中" : `共 ${details.total.toLocaleString()} 筆`}
                </span>
              </div>
              <div className="page-actions">
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => setDetailsPage((current) => Math.max(1, current - 1))}
                  disabled={detailsPage <= 1 || detailsLoading}
                >
                  上一頁
                </button>
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => setDetailsPage((current) => Math.min(maxDetailsPage, current + 1))}
                  disabled={detailsPage >= maxDetailsPage || detailsLoading}
                >
                  下一頁
                </button>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>房號</th>
                    <th>電費</th>
                    <th>電費金額</th>
                    <th>狀態</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {details.rows.map((row) => {
                    const line = electricityLine(row);
                    return (
                      <tr key={row.detail_id}>
                        <td>{row.room_code ?? `#${row.room_id}`}</td>
                        <td>{line?.charge_type ?? "電費"}</td>
                        <td>{formatMoney(line?.amount ?? row.subtotal)}</td>
                        <td>
                          <span className={detailStatusPillClass(row.status)}>
                            {formatDetailStatus(row.status)}
                          </span>
                        </td>
                        <td>{extractReason(row)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!details.rows.length ? (
                <div className="empty-state">
                  {detailsLoading ? "讀取試算明細中" : "目前沒有試算明細"}
                </div>
              ) : null}
            </div>
            <div className="pagination">
              <div className="page-size">
                <span className="muted">每頁</span>
                <select
                  className="control"
                  value={detailsSize}
                  onChange={(event) => changeDetailsSize(Number(event.target.value))}
                  disabled={detailsLoading}
                >
                  {PAGE_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {size} 筆
                    </option>
                  ))}
                </select>
                <span className="muted">
                  第 {detailsPage} / {maxDetailsPage} 頁
                </span>
              </div>
              <span className="muted">{detailsLoading ? "更新中" : null}</span>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
