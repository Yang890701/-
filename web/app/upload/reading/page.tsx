"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../../lib/api";

type MasterList<T> = {
  rows: T[];
  total: number;
};

type Room = {
  id: number;
  room_code: string;
  room_name: string | null;
};

type Meter = {
  id: number;
  electricity_code: string;
  name: string | null;
};

type MeterAssignment = {
  id: number;
  room_id: number;
  meter_id: number;
  meter_category: string;
  effective_from_ym: string;
  effective_to_ym: string | null;
  initial_reading: number | null;
};

type MeterReading = {
  id: number;
  assignment_id: number;
  billing_ym: string;
  reading_kind: string;
  reading: number;
  attachment_id: number | null;
  created_at: string;
};

type ReadingException = {
  id: number;
  assignment_id: number;
  billing_ym: string;
  reason: string;
  status: string;
  created_at: string;
};

type ReadingSubmitResponse =
  | {
      kind: "meter_reading";
      row: MeterReading;
    }
  | {
      kind: "reading_exception";
      row: ReadingException;
    };

function formatRoom(room: Room | undefined) {
  if (!room) {
    return "未知房號";
  }
  return room.room_name ? `${room.room_code} ${room.room_name}` : room.room_code;
}

function formatMeter(meter: Meter | undefined) {
  if (!meter) {
    return "未知電表";
  }
  return meter.name ? `${meter.electricity_code} ${meter.name}` : meter.electricity_code;
}

function formatAssignment(
  assignment: MeterAssignment,
  roomsById: Map<number, Room>,
  metersById: Map<number, Meter>,
) {
  const toYm = assignment.effective_to_ym ? `-${assignment.effective_to_ym}` : "";
  return `${formatRoom(roomsById.get(assignment.room_id))} / ${formatMeter(
    metersById.get(assignment.meter_id),
  )} / ${assignment.meter_category} / ${assignment.effective_from_ym}${toYm}`;
}

function formatReading(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : value.toLocaleString();
}

export default function ReadingUploadPage() {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [meters, setMeters] = useState<Meter[]>([]);
  const [assignments, setAssignments] = useState<MeterAssignment[]>([]);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState("");
  const [billingYm, setBillingYm] = useState("");
  const [readingKind, setReadingKind] = useState("例行");
  const [readingValue, setReadingValue] = useState("");
  const [note, setNote] = useState("");
  const [fileNote, setFileNote] = useState("");
  const [readings, setReadings] = useState<MeterReading[]>([]);
  const [exceptions, setExceptions] = useState<ReadingException[]>([]);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"success" | "warning">("success");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const roomsById = useMemo(() => new Map(rooms.map((room) => [room.id, room])), [rooms]);
  const metersById = useMemo(() => new Map(meters.map((meter) => [meter.id, meter])), [meters]);

  const selectedAssignment = useMemo(
    () => assignments.find((assignment) => String(assignment.id) === selectedAssignmentId),
    [assignments, selectedAssignmentId],
  );

  const loadExceptions = useCallback(async () => {
    const response = await apiJson<MasterList<ReadingException>>("/api/reading-exceptions?status=open");
    setExceptions(response.rows);
  }, []);

  const loadReadings = useCallback(async (assignmentId: string) => {
    if (!assignmentId) {
      setReadings([]);
      return;
    }
    const response = await apiJson<MasterList<MeterReading>>(
      `/api/meter-readings?assignment_id=${assignmentId}`,
    );
    setReadings(response.rows);
  }, []);

  const loadReferenceData = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const [roomResponse, meterResponse, assignmentResponse] = await Promise.all([
        apiJson<MasterList<Room>>("/api/master/room"),
        apiJson<MasterList<Meter>>("/api/master/meter"),
        apiJson<MasterList<MeterAssignment>>("/api/meter-assignments"),
      ]);
      setRooms(roomResponse.rows);
      setMeters(meterResponse.rows);
      setAssignments(assignmentResponse.rows);
      setSelectedAssignmentId((current) => current || String(assignmentResponse.rows[0]?.id ?? ""));
      await loadExceptions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "讀取資料失敗");
    } finally {
      setIsLoading(false);
    }
  }, [loadExceptions]);

  useEffect(() => {
    loadReferenceData();
  }, [loadReferenceData]);

  useEffect(() => {
    loadReadings(selectedAssignmentId).catch((err) => {
      setError(err instanceof Error ? err.message : "讀取近期度數失敗");
    });
  }, [loadReadings, selectedAssignmentId]);

  async function submitReading(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAssignmentId) {
      setError("請先選擇房號電表關聯");
      return;
    }
    const trimmedReading = readingValue.trim();
    const parsedReading = trimmedReading ? Number(trimmedReading) : null;
    if (parsedReading !== null && !Number.isFinite(parsedReading)) {
      setError("度數必須是數字");
      return;
    }

    const trimmedNote = note.trim();
    const mergedNote =
      fileNote && trimmedNote ? `${trimmedNote} / 附件備註: ${fileNote}` : trimmedNote || fileNote || null;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await apiJson<ReadingSubmitResponse>("/api/meter-readings", {
        method: "POST",
        body: JSON.stringify({
          assignment_id: Number(selectedAssignmentId),
          billing_ym: billingYm,
          reading_kind: readingKind,
          reading: parsedReading,
          note: mergedNote,
        }),
      });
      if (response.kind === "reading_exception") {
        setMessageTone("warning");
        setMessage(`已建立例外佇列: ${response.row.reason}`);
      } else {
        setMessageTone("success");
        setMessage("度數已上傳");
        setReadingValue("");
      }
      await Promise.all([loadReadings(selectedAssignmentId), loadExceptions()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "度數上傳失敗");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="card master-header">
        <div>
          <p className="portal-kicker">電費資料</p>
          <h1 className="section-title">房號度數上傳</h1>
          <p className="muted">房號、電表與期別讀數</p>
        </div>
        <div className="master-header-actions">
          <button className="button button-secondary" type="button" onClick={loadReferenceData}>
            重新整理
          </button>
        </div>
      </section>

      <section className="card master-form-card">
        <form className="master-form" onSubmit={submitReading}>
          <div className="master-form-heading">
            <strong>上傳度數</strong>
            {selectedAssignment ? (
              <span className="muted">
                初始 {formatReading(selectedAssignment.initial_reading)} / 起始期{" "}
                {selectedAssignment.effective_from_ym}
              </span>
            ) : null}
          </div>
          <div className="master-form-grid">
            <label className="field">
              <span>
                房號電表關聯 <span className="required-mark">*</span>
              </span>
              <select
                className="control"
                value={selectedAssignmentId}
                onChange={(event) => setSelectedAssignmentId(event.target.value)}
                required
              >
                <option value="">請選擇</option>
                {assignments.map((assignment) => (
                  <option key={assignment.id} value={assignment.id}>
                    {formatAssignment(assignment, roomsById, metersById)}
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
                讀數類型 <span className="required-mark">*</span>
              </span>
              <select
                className="control"
                value={readingKind}
                onChange={(event) => setReadingKind(event.target.value)}
              >
                <option value="例行">例行</option>
                <option value="初始">初始</option>
              </select>
            </label>
            <label className="field">
              <span>度數</span>
              <input
                className="control"
                inputMode="numeric"
                value={readingValue}
                onChange={(event) => setReadingValue(event.target.value)}
              />
            </label>
            <label className="field">
              <span>備註</span>
              <input
                className="control"
                value={note}
                onChange={(event) => setNote(event.target.value)}
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
      {message ? <div className={`message message-${messageTone}`}>{message}</div> : null}

      <section className="card table-card">
        <div className="pagination">
          <div>
            <strong>近期度數</strong>
            <span className="muted"> {isLoading ? "讀取中" : `${readings.length.toLocaleString()} 筆`}</span>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>帳單年月</th>
                <th>類型</th>
                <th>度數</th>
                <th>附件</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((reading) => (
                <tr key={reading.id}>
                  <td>{reading.billing_ym}</td>
                  <td>{reading.reading_kind}</td>
                  <td>{reading.reading.toLocaleString()}</td>
                  <td>{reading.attachment_id ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!readings.length ? <div className="empty-state">尚無度數</div> : null}
        </div>
      </section>

      <section className="card table-card">
        <div className="pagination">
          <div>
            <strong>開放例外</strong>
            <span className="muted"> {exceptions.length.toLocaleString()} 筆</span>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>關聯ID</th>
                <th>帳單年月</th>
                <th>原因</th>
                <th>狀態</th>
              </tr>
            </thead>
            <tbody>
              {exceptions.map((item) => (
                <tr key={item.id}>
                  <td>{item.assignment_id}</td>
                  <td>{item.billing_ym}</td>
                  <td>{item.reason}</td>
                  <td>{item.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!exceptions.length ? <div className="empty-state">尚無開放例外</div> : null}
        </div>
      </section>
    </main>
  );
}
