export type ToolCall = {
  name: string;
  args: unknown;
  response?: unknown;
};

export type ChatResponse = {
  userId: string;
  sessionId: string;
  answer: string;
  thoughts: string;
  tools: ToolCall[];
};

export type SessionSummary = {
  sessionId: string;
  title: string;
  lastUpdate?: string | null;
};

export type HistoryMessage =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      answer: string;
      thoughts: string;
      tools: ToolCall[];
    };

export type HistoryResponse = {
  userId: string;
  sessionId: string;
  messages: HistoryMessage[];
};

async function readErrorMessage(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : "Error del servidor.";
}

async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return (await res.json()) as T;
}

export async function sendChat(
  message: string,
  userId: string | null,
  sessionId: string | null,
): Promise<ChatResponse> {
  return fetchJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      userId: userId ?? undefined,
      sessionId: sessionId ?? undefined,
    }),
  });
}

export async function listSessions(userId: string): Promise<SessionSummary[]> {
  return fetchJson<SessionSummary[]>(`/api/sessions?userId=${encodeURIComponent(userId)}`);
}

export async function getSessionHistory(
  userId: string,
  sessionId: string,
): Promise<HistoryResponse> {
  return fetchJson<HistoryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}?userId=${encodeURIComponent(userId)}`,
  );
}

export async function deleteSession(userId: string, sessionId: string): Promise<void> {
  await fetchJson<{ status: string }>(
    `/api/sessions/${encodeURIComponent(sessionId)}?userId=${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
}
