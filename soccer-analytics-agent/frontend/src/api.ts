import type { ChatResponse, TraceResponse, ToolCall } from "./lib/types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function fetchJson<T>(
  url: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = 30_000, ...fetchInit } = init ?? {};

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const res = await fetch(url, { ...fetchInit, signal: ctrl.signal });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail =
        typeof body?.detail === "string"
          ? body.detail
          : body?.message ?? `Error ${res.status}`;
      throw new ApiError(detail, res.status);
    }
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timer);
  }
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

/** Fetch the full trace for a session. Short timeout — trace data lands before the chat response returns. */
export async function getTrace(
  sessionId: string,
): Promise<TraceResponse> {
  return fetchJson<TraceResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/trace`,
    { timeoutMs: 5_000 },
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

export interface StreamHandlers {
  onToolCall: (calls: ToolCall[]) => void;
  onDelta: (text: string) => void;
  onDone: (ev: { session_id: string; turn_id: number; answer: string }) => void;
  onError: (ev: { status: number; detail: string }) => void;
}

/**
 * Send a chat message and stream the response over Server-Sent Events.
 * Dispatches `tool_call`, `delta`, `done` and `error` frames to `handlers`
 * as they arrive. Pass `signal` to cancel an in-flight stream (e.g. on
 * unmount or when the user sends a new message).
 */
export async function sendChatStream(
  text: string,
  sessionId: string | null,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    throw err;
  }

  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : body?.message ?? `Error ${res.status}`;
    handlers.onError({ status: res.status, detail });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function dispatch(eventType: string, data: string) {
    if (!eventType || !data) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(data);
    } catch {
      return;
    }

    switch (eventType) {
      case "tool_call": {
        const rawCalls = (parsed.calls as Array<Record<string, unknown>>) ?? [];
        const calls: ToolCall[] = rawCalls.map((raw) => ({
          name: raw.tool as string,
          args: raw.args as Record<string, unknown>,
          result: raw.result as Record<string, unknown>,
        }));
        handlers.onToolCall(calls);
        break;
      }
      case "delta":
        handlers.onDelta(parsed.text as string);
        break;
      case "done":
        handlers.onDone(
          parsed as { session_id: string; turn_id: number; answer: string },
        );
        break;
      case "error":
        handlers.onError(parsed as { status: number; detail: string });
        break;
      default:
        break;
    }
  }

  function processBuffer() {
    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);

      let eventType = "";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      dispatch(eventType, dataLines.join("\n"));
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      processBuffer();
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    throw err;
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
