export type ToolCall = {
  name: string;
  args: unknown;
  response?: unknown;
};

export type ChatResponse = {
  session_id: string;
  answer: string;
  tools: ToolCall[];
};

export type MemoryItem = {
  role: string;
  content: string;
};

export type TraceStep = {
  step: number;
  kind: string;
  content: unknown;
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function sendChat(
  message: string,
  sessionId: string,
): Promise<ChatResponse> {
  return fetchJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export async function getMemory(sessionId: string): Promise<MemoryItem[]> {
  return fetchJson<MemoryItem[]>(`/api/sessions/${encodeURIComponent(sessionId)}/memory`);
}

export async function getTrace(sessionId: string): Promise<TraceStep[]> {
  return fetchJson<TraceStep[]>(`/api/sessions/${encodeURIComponent(sessionId)}/trace`);
}
