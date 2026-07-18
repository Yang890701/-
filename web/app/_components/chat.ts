// 問答共用邏輯:對話歷史組裝 + SSE 串流問答。
// genie 面板與 /assistant 頁共用,避免兩套實作漂移。

import { apiFetch } from "../../lib/api";

export type HistoryMsg = { role: "user" | "assistant"; content: string };

type TurnLike = { q: string; answer?: string; error?: string; pending?: boolean };

const MAX_TURNS = 6;
const MAX_ANSWER_CHARS = 800;

export function turnsToHistory(turns: TurnLike[]): HistoryMsg[] {
  return turns
    .filter((t) => !t.pending && !t.error && t.answer)
    .slice(-MAX_TURNS)
    .flatMap((t) => [
      { role: "user" as const, content: t.q },
      { role: "assistant" as const, content: (t.answer as string).slice(0, MAX_ANSWER_CHARS) },
    ]);
}

type AskBody = { question: string; context?: string; history?: HistoryMsg[] };
type AskEvent =
  | { type: "status"; label: string }
  | { type: "final"; payload: unknown }
  | { type: "error"; message: string };

// SSE 串流問答:過程用 onStatus 回報「正在查什麼」,resolve 出最終答案。
export async function askStream<T>(body: AskBody, onStatus: (label: string) => void): Promise<T> {
  const res = await apiFetch("/api/assistant/ask/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const message = await res
      .json()
      .then((b) => b.detail ?? "查詢失敗")
      .catch(() => "查詢失敗");
    throw new Error(String(message));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let final: T | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const ev = JSON.parse(line.slice(6)) as AskEvent;
      if (ev.type === "status") onStatus(ev.label);
      else if (ev.type === "final") final = ev.payload as T;
      else throw new Error(ev.message);
    }
  }
  if (final === null) throw new Error("連線中斷,請再問一次");
  return final;
}
