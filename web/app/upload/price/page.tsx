"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../../lib/api";

type MasterList<T> = {
  rows: T[];
  total: number;
};

type Meter = {
  id: number;
  electricity_code: string;
  name: string | null;
};

type AvgPrice = {
  id: number;
  meter_id: number;
  billing_ym: string;
  price: string;
  attachment_id: number | null;
  created_at: string;
};

function formatMeter(meter: Meter | undefined) {
  if (!meter) {
    return "未知電表";
  }
  return meter.name ? `${meter.electricity_code} ${meter.name}` : meter.electricity_code;
}

export default function PriceUploadPage() {
  const [meters, setMeters] = useState<Meter[]>([]);
  const [selectedMeterId, setSelectedMeterId] = useState("");
  const [billingYm, setBillingYm] = useState("");
  const [price, setPrice] = useState("");
  const [fileNote, setFileNote] = useState("");
  const [prices, setPrices] = useState<AvgPrice[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const metersById = useMemo(() => new Map(meters.map((meter) => [meter.id, meter])), [meters]);

  const loadPrices = useCallback(async (meterId: string) => {
    const query = meterId ? `?meter_id=${meterId}` : "";
    const response = await apiJson<MasterList<AvgPrice>>(`/api/avg-prices${query}`);
    setPrices(response.rows);
  }, []);

  const loadMeters = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const response = await apiJson<MasterList<Meter>>("/api/master/meter");
      setMeters(response.rows);
      setSelectedMeterId((current) => current || String(response.rows[0]?.id ?? ""));
    } catch (err) {
      setError(err instanceof Error ? err.message : "讀取電表失敗");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMeters();
  }, [loadMeters]);

  useEffect(() => {
    loadPrices(selectedMeterId).catch((err) => {
      setError(err instanceof Error ? err.message : "讀取平均電價失敗");
    });
  }, [loadPrices, selectedMeterId]);

  async function submitPrice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedMeterId) {
      setError("請先選擇電表");
      return;
    }
    const parsedPrice = Number(price);
    if (!Number.isFinite(parsedPrice) || parsedPrice < 0) {
      setError("平均電價必須是非負數字");
      return;
    }

    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await apiJson<AvgPrice>("/api/avg-prices", {
        method: "POST",
        body: JSON.stringify({
          meter_id: Number(selectedMeterId),
          billing_ym: billingYm,
          price,
        }),
      });
      setMessage(fileNote ? `平均電價已上傳，附件備註: ${fileNote}` : "平均電價已上傳");
      setPrice("");
      await loadPrices(String(response.meter_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "平均電價上傳失敗");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="card master-header">
        <div>
          <p className="portal-kicker">電費資料</p>
          <h1 className="section-title">平均電價上傳</h1>
          <p className="muted">台電帳單年月與平均電價</p>
        </div>
        <div className="master-header-actions">
          <button className="button button-secondary" type="button" onClick={loadMeters}>
            重新整理
          </button>
        </div>
      </section>

      <section className="card master-form-card">
        <form className="master-form" onSubmit={submitPrice}>
          <div className="master-form-heading">
            <strong>上傳電價</strong>
            {selectedMeterId ? <span className="muted">{formatMeter(metersById.get(Number(selectedMeterId)))}</span> : null}
          </div>
          <div className="master-form-grid">
            <label className="field">
              <span>
                電表 <span className="required-mark">*</span>
              </span>
              <select
                className="control"
                value={selectedMeterId}
                onChange={(event) => setSelectedMeterId(event.target.value)}
                required
              >
                <option value="">請選擇</option>
                {meters.map((meter) => (
                  <option key={meter.id} value={meter.id}>
                    {formatMeter(meter)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>
                帳單年月 <span className="required-mark">*</span>
              </span>
              <input
                className="control"
                inputMode="numeric"
                maxLength={6}
                placeholder="202607"
                value={billingYm}
                onChange={(event) => setBillingYm(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>
                平均電價 <span className="required-mark">*</span>
              </span>
              <input
                className="control"
                inputMode="decimal"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>附件備註</span>
              <input
                className="control"
                type="file"
                onChange={(event) => setFileNote(event.target.files?.[0]?.name ?? "")}
              />
            </label>
          </div>
          <div className="master-form-actions">
            <button className="button button-primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "上傳中" : "上傳"}
            </button>
          </div>
        </form>
      </section>

      {error ? <div className="error">{error}</div> : null}
      {message ? <div className="message message-success">{message}</div> : null}

      <section className="card table-card">
        <div className="pagination">
          <div>
            <strong>近期平均電價</strong>
            <span className="muted"> {isLoading ? "讀取中" : `${prices.length.toLocaleString()} 筆`}</span>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>電表</th>
                <th>帳單年月</th>
                <th>平均電價</th>
                <th>附件</th>
              </tr>
            </thead>
            <tbody>
              {prices.map((item) => (
                <tr key={item.id}>
                  <td>{formatMeter(metersById.get(item.meter_id))}</td>
                  <td>{item.billing_ym}</td>
                  <td>{item.price}</td>
                  <td>{item.attachment_id ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!prices.length ? <div className="empty-state">尚無平均電價</div> : null}
        </div>
      </section>
    </main>
  );
}
