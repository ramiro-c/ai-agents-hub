import type { ChatResponse, TraceResponse, ToolCall } from "./lib/types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : body?.message ?? `Error ${res.status}`;
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

/** Send a chat message. Returns {session_id, answer}. */
export async function sendChat(
  text: string,
  sessionId: string,
): Promise<ChatResponse> {
  return fetchJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, session_id: sessionId }),
  });
}

/** Fetch the full trace for a session. */
export async function getTrace(
  sessionId: string,
): Promise<TraceResponse> {
  return fetchJson<TraceResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/trace`,
  );
}

/** Check backend health. */
export async function getHealth(): Promise<{ status: string }> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 5_000);
    const res = await fetch("/api/health", { signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as { status: string };
  } catch {
    throw new Error("Health check failed");
  }
}

/**
 * Poll the trace endpoint after a chat response, retrying up to `retries` times
 * with `intervalMs` between polls. Resolves with parsed ToolCall[] or null if
 * nothing new arrives.
 */
export async function pollTrace(
  sessionId: string,
  turnId: number,
  retries = 3,
  intervalMs = 500,
): Promise<ToolCall[] | null> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (attempt > 0) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    try {
      const trace = await getTrace(sessionId);
      // Filter steps belonging to this turn that contain tool calls
      const calls: ToolCall[] = [];
      for (const step of trace.trace) {
        if (
          step.turn_id === turnId &&
          step.content.kind === "tool_calls"
        ) {
          for (const raw of step.content.calls) {
            calls.push({
              name: raw.tool,
              args: raw.args,
              result: raw.result,
            });
          }
        }
      }
      if (calls.length > 0) return calls;
    } catch {
      // Trace endpoint error — keep retrying
    }
  }
  return null;
}
