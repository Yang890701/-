// 問答輪次 → 後端 /api/assistant/ask 的對話歷史。
// 只帶已完成的輪次、最近 6 輪、答案截斷,支援「那二月呢」式追問。

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
