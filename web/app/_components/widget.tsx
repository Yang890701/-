"use client";

// 儀表板 widget 渲染器(kpi / bar / line / pie / stacked-bar / table)。
// 純 SVG/CSS,不依賴圖表套件;視覺參考 Tableau 10 配色與 BI 儀表板慣例。
// 後端 present/dashboard 回傳的 widget 物件直接丟進來即可。

export type Widget = {
  type: "kpi" | "bar" | "line" | "pie" | "stacked-bar" | "table";
  title?: string;
  label?: string;
  value?: number;
  unit?: string;
  delta?: number; // 相對上期 %(選填,KPI 用)
  data?: Record<string, unknown>[];
  columns?: string[];
  rows?: Record<string, unknown>[];
};

const PALETTE = [
  "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
  "#EDC949", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
];

/* ---------- 數值/標籤工具 ---------- */

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function labelOf(row: Record<string, unknown>): string {
  const k = row.name ?? row.group ?? row.x ?? row.label;
  if (k !== undefined && k !== null) return String(k);
  const s = Object.values(row).find((v) => typeof v === "string");
  return s ? String(s) : "";
}

// 容錯:AI 可能把數值放在 value 以外的欄位(avg/total/amount…),取第一個數值欄
function valueOf(row: Record<string, unknown>): number {
  if (row.value !== undefined) return num(row.value);
  for (const [k, v] of Object.entries(row)) {
    if (k === "name" || k === "group" || k === "x" || k === "label") continue;
    const n = Number(v);
    if (typeof v !== "boolean" && Number.isFinite(n)) return n;
  }
  return 0;
}

function fmtFull(v: number): string {
  return Number.isInteger(v)
    ? v.toLocaleString()
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

// 中文縮寫:52,900 → 5.3萬;1.2億
function fmtCompact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e8) return `${(v / 1e8).toFixed(1).replace(/\.0$/, "")}億`;
  if (a >= 1e4) return `${(v / 1e4).toFixed(1).replace(/\.0$/, "")}萬`;
  return fmtFull(v);
}

// 202603 → 2026/03
function fmtX(s: string): string {
  return /^\d{6}$/.test(s) ? `${s.slice(0, 4)}/${s.slice(4)}` : s;
}

/* ---------- 座標軸刻度 ---------- */

function niceNum(range: number, round: boolean): number {
  const exp = Math.floor(Math.log10(Math.max(range, 1e-9)));
  const f = range / 10 ** exp;
  let nf: number;
  if (round) nf = f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10;
  else nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return nf * 10 ** exp;
}

function makeTicks(lo: number, hi: number, count = 4): number[] {
  if (hi === lo) hi = lo + 1;
  const step = niceNum(niceNum(hi - lo, false) / (count - 1), true);
  const start = Math.floor(lo / step) * step;
  const out: number[] = [];
  for (let v = start; v <= hi + step / 2; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

/* ---------- 折線圖(修平線:Y 軸 min–max 自動縮放) ---------- */

function smoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length < 2) return pts.length ? `M ${pts[0].x} ${pts[0].y}` : "";
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

function LineChart({ data, id }: { data: Record<string, unknown>[]; id: string }) {
  if (!data.length) return <div className="muted">無資料</div>;
  const W = 560;
  const H = 230;
  const M = { top: 18, right: 18, bottom: 30, left: 52 };
  const values = data.map(valueOf);
  const dmin = Math.min(...values);
  const dmax = Math.max(...values);
  // 全正值且變動幅度大 → 從 0 起;變動小(平線元兇)→ 用 min–max 放大差異
  const allPos = dmin >= 0;
  const lo = allPos && dmin <= dmax * 0.35 ? 0 : dmin - (dmax - dmin || Math.abs(dmax) || 1) * 0.15;
  const hi = dmax + (dmax - dmin || Math.abs(dmax) || 1) * 0.12;
  const ticks = makeTicks(lo, hi);
  const yLo = ticks[0];
  const yHi = ticks[ticks.length - 1];
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const xOf = (i: number) => M.left + (data.length > 1 ? (plotW * i) / (data.length - 1) : plotW / 2);
  const yOf = (v: number) => M.top + plotH - ((v - yLo) / (yHi - yLo || 1)) * plotH;
  const pts = data.map((row, i) => ({ x: xOf(i), y: yOf(valueOf(row)), row }));
  const line = smoothPath(pts);
  const area = `${line} L ${pts[pts.length - 1].x.toFixed(1)} ${(M.top + plotH).toFixed(1)} L ${pts[0].x.toFixed(1)} ${(M.top + plotH).toFixed(1)} Z`;
  const xEvery = Math.max(1, Math.ceil(data.length / 7));
  const showPointLabels = data.length <= 8;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img">
      <defs>
        <linearGradient id={`grad-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={PALETTE[0]} stopOpacity="0.28" />
          <stop offset="100%" stopColor={PALETTE[0]} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.left} y1={yOf(t)} x2={W - M.right} y2={yOf(t)} stroke="#ecebe6" strokeDasharray="3 3" />
          <text x={M.left - 8} y={yOf(t) + 3.5} fontSize={10.5} textAnchor="end" fill="#8a8f94">
            {fmtCompact(t)}
          </text>
        </g>
      ))}
      <path d={area} fill={`url(#grad-${id})`} />
      <path d={line} fill="none" stroke={PALETTE[0]} strokeWidth={2.4} strokeLinecap="round" />
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={4} fill="#fff" stroke={PALETTE[0]} strokeWidth={2} />
          {showPointLabels ? (
            <text x={p.x} y={p.y - 9} fontSize={10.5} textAnchor="middle" fill="#46515b" fontWeight={600}>
              {fmtCompact(valueOf(p.row))}
            </text>
          ) : null}
          {i % xEvery === 0 || i === data.length - 1 ? (
            <text x={p.x} y={H - 8} fontSize={10.5} textAnchor="middle" fill="#8a8f94">
              {fmtX(labelOf(p.row))}
            </text>
          ) : null}
        </g>
      ))}
    </svg>
  );
}

/* ---------- 長條圖(SVG:X 軸刻度+格線+條末數值;top-N,其餘以註記呈現) ---------- */

const MAX_BARS = 10;

function collapse(data: Record<string, unknown>[], max: number): Record<string, unknown>[] {
  if (data.length <= max) return data;
  const sorted = [...data].sort((a, b) => valueOf(b) - valueOf(a));
  const head = sorted.slice(0, max - 1);
  const rest = sorted.slice(max - 1);
  return [...head, { group: `其他(${rest.length}項)`, value: rest.reduce((s, r) => s + valueOf(r), 0) }];
}

function truncateLabel(s: string, max = 8): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function BarChart({ data }: { data: Record<string, unknown>[] }) {
  if (!data.length) return <div className="muted">無資料</div>;
  const sorted = [...data].sort((a, b) => valueOf(b) - valueOf(a));
  const rows = sorted.slice(0, MAX_BARS);
  const rest = sorted.slice(MAX_BARS);
  const restSum = rest.reduce((s, r) => s + valueOf(r), 0);

  const W = 560;
  const M = { top: 24, right: 58, bottom: 8, left: 116 };
  const rowH = 30;
  const H = M.top + rows.length * rowH + M.bottom;
  const plotW = W - M.left - M.right;
  const maxV = Math.max(1, ...rows.map(valueOf));
  const ticks = makeTicks(0, maxV * 1.02, 4).filter((t) => t >= 0);
  const xHi = ticks[ticks.length - 1] || 1;
  const xOf = (v: number) => M.left + (v / xHi) * plotW;

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img">
        {/* X 軸刻度與垂直格線 */}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={xOf(t)} y1={M.top - 4} x2={xOf(t)} y2={H - M.bottom} stroke="#ecebe6" strokeDasharray="3 3" />
            <text x={xOf(t)} y={M.top - 10} fontSize={10.5} textAnchor="middle" fill="#8a8f94">
              {fmtCompact(t)}
            </text>
          </g>
        ))}
        {rows.map((row, i) => {
          const v = valueOf(row);
          const y = M.top + i * rowH;
          const barW = Math.max((v / xHi) * plotW, 2);
          const label = labelOf(row);
          return (
            <g key={i}>
              <title>{`${label}:${fmtFull(v)}`}</title>
              <text x={M.left - 8} y={y + rowH / 2 + 4} fontSize={12} textAnchor="end" fill="#46515b">
                {truncateLabel(label)}
              </text>
              <rect x={M.left} y={y + (rowH - 17) / 2} width={barW} height={17} rx={4} fill={PALETTE[i % PALETTE.length]} />
              <text x={M.left + barW + 6} y={y + rowH / 2 + 4} fontSize={11.5} fill="#31373d" fontWeight={600}>
                {fmtCompact(v)}
              </text>
            </g>
          );
        })}
      </svg>
      {rest.length ? (
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          另有 {rest.length} 項未列入(合計 {fmtCompact(restSum)}),僅顯示前 {MAX_BARS} 名。
        </div>
      ) : null}
    </>
  );
}

/* ---------- 環圈圖(donut,中心合計) ---------- */

function DonutChart({ data }: { data: Record<string, unknown>[] }) {
  const rows = collapse(data.filter((r) => valueOf(r) > 0), 6);
  const total = rows.reduce((s, r) => s + valueOf(r), 0);
  if (!rows.length || total <= 0) return <div className="muted">無資料</div>;
  const cx = 70, cy = 70, r = 58, inner = 36;
  let acc = 0;
  const slices = rows.map((row, i) => {
    const frac = valueOf(row) / total;
    const a0 = acc * 2 * Math.PI - Math.PI / 2;
    acc += frac;
    const a1 = Math.min(acc, 0.99999) * 2 * Math.PI - Math.PI / 2;
    const large = frac > 0.5 ? 1 : 0;
    const p = (ang: number, rad: number) => `${(cx + rad * Math.cos(ang)).toFixed(2)} ${(cy + rad * Math.sin(ang)).toFixed(2)}`;
    const d = `M ${p(a0, r)} A ${r} ${r} 0 ${large} 1 ${p(a1, r)} L ${p(a1, inner)} A ${inner} ${inner} 0 ${large} 0 ${p(a0, inner)} Z`;
    return { d, color: PALETTE[i % PALETTE.length], row, frac };
  });
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 140 140" width={160} height={160}>
        {slices.map((s, i) => (
          <path key={i} d={s.d} fill={s.color} stroke="#fff" strokeWidth={1.5} />
        ))}
        <text x={cx} y={cy - 2} fontSize={15} fontWeight={700} textAnchor="middle" fill="#26313b">
          {fmtCompact(total)}
        </text>
        <text x={cx} y={cy + 14} fontSize={10} textAnchor="middle" fill="#8a8f94">
          合計
        </text>
      </svg>
      <div className="donut-legend">
        {slices.map((s, i) => (
          <div key={i} className="donut-legend-row">
            <span className="donut-swatch" style={{ background: s.color }} />
            <span className="donut-name">{labelOf(s.row)}</span>
            <span className="donut-val">
              {fmtCompact(valueOf(s.row))}
              <span className="muted">({Math.round(s.frac * 100)}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- 表格 ---------- */

function TableWidget({ widget }: { widget: Widget }) {
  const rows = widget.rows ?? widget.data ?? [];
  const cols = widget.columns ?? (rows[0] ? Object.keys(rows[0]) : []);
  if (!rows.length) return <div className="muted">無資料</div>;
  return (
    <div className="table-scroll" style={{ maxHeight: 320 }}>
      <table>
        <thead>
          <tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => {
                const v = row[c];
                const isNum = typeof v === "number";
                return (
                  <td key={c} style={isNum ? { textAlign: "right", fontVariantNumeric: "tabular-nums" } : undefined}>
                    {v === null || v === undefined || v === "" ? "－" : isNum ? fmtFull(v as number) : String(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- KPI ---------- */

function KpiCard({ widget }: { widget: Widget }) {
  const delta = widget.delta;
  return (
    <div className="card kpi-card">
      <div className="kpi-label">{widget.label}</div>
      <div className="kpi-value">
        {fmtFull(num(widget.value))}
        {widget.unit ? <span className="kpi-unit">{widget.unit}</span> : null}
      </div>
      {delta !== undefined && delta !== null ? (
        <div className={`kpi-delta ${delta >= 0 ? "kpi-delta-up" : "kpi-delta-down"}`}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
          <span className="muted"> vs 上月</span>
        </div>
      ) : null}
    </div>
  );
}

/* ---------- 對外元件 ---------- */

let uid = 0;

export function WidgetView({ widget }: { widget: Widget }) {
  if (widget.type === "kpi") return <KpiCard widget={widget} />;
  // 容錯:AI 偶爾把數據放進 rows 而非 data
  const data = widget.data?.length ? widget.data : (widget.rows ?? []);
  const id = String(uid++);
  return (
    <div className="card chart-card">
      {widget.title ? <div className="chart-title">{widget.title}</div> : null}
      {widget.type === "line" ? (
        <LineChart data={data} id={id} />
      ) : widget.type === "pie" ? (
        <DonutChart data={data} />
      ) : widget.type === "table" ? (
        <TableWidget widget={widget} />
      ) : (
        <BarChart data={data} />
      )}
    </div>
  );
}

export function WidgetGrid({ widgets }: { widgets: Widget[] }) {
  if (!widgets?.length) return null;
  const kpis = widgets.filter((w) => w.type === "kpi");
  const rest = widgets.filter((w) => w.type !== "kpi");
  return (
    <div className="widget-stack">
      {kpis.length ? (
        <div className="kpi-row">
          {kpis.map((w, i) => <WidgetView key={i} widget={w} />)}
        </div>
      ) : null}
      {rest.length ? (
        <div className="dash-grid">
          {rest.map((w, i) => <WidgetView key={i} widget={w} />)}
        </div>
      ) : null}
    </div>
  );
}
