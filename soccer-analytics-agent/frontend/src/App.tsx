import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HealthPill } from "./components/HealthPill";
import { ChatColumn } from "./components/ChatColumn";
import { AnalyticsPanel } from "./components/AnalyticsPanel";
import { buildSnapshot } from "./lib/analytics";
import { sendChat, pollTrace, getHealth, ApiError } from "./api";
import type { HealthStatus, Message } from "./lib/types";

const SESSION_KEY = "soccer_agent_session_id";

let msgCounter = 0;
const nextId = () => `m${++msgCounter}-${Date.now()}`;

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    // fallback for environments without crypto
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

function initSessionId(): string {
  try {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) return stored;
    const id = uid();
    localStorage.setItem(SESSION_KEY, id);
    return id;
  } catch {
    // localStorage unavailable — use in-memory only
    console.warn(
      "localStorage is not available. Session ID will not persist across tabs.",
    );
    return uid();
  }
}

export default function App() {
  const [sessionId, setSessionId] = useState(initSessionId);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("connecting");
  const geminiModel = 'gemini-2.5-flash';
  const sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;

  // ── Health polling (T-025) ──
  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        await getHealth();
        if (active) setHealthStatus("healthy");
      } catch {
        if (active) setHealthStatus("unhealthy");
      }
    }

    poll();
    const id = window.setInterval(poll, 20_000);

    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  // ── Send message handler (T-023 + T-024) ──
  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      const sid = sessionRef.current;
      const userMsg: Message = { id: nextId(), role: "user", text: trimmed };

      // Optimistic: show user message immediately
      setMessages((prev) => [...prev, userMsg]);
      setBusy(true);

      try {
        // 1. Send to backend
        const chatResp = await sendChat(trimmed, sid);

        // Update session ID if backend gave a new one
        if (chatResp.session_id && chatResp.session_id !== sid) {
          setSessionId(chatResp.session_id);
          try {
            localStorage.setItem(SESSION_KEY, chatResp.session_id);
          } catch {
            /* storage unavailable */
          }
        }

        // 2. Use the server-authoritative turn id (never guess it client-side —
        //    a local counter desyncs from the backend after a reload).
        const turnId = chatResp.turn_id;

        const assistantMsg: Message = {
          id: nextId(),
          role: "assistant",
          text: chatResp.answer || "(empty reply)",
          traceStatus: "loading",
        };

        setMessages((prev) => [...prev, assistantMsg]);

        // 3. Poll trace endpoint for tool calls
        const currentSid = chatResp.session_id || sid;
        const trace = await pollTrace(currentSid, turnId);

        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant") {
            return [
              ...prev.slice(0, -1),
              {
                ...last,
                trace: trace ?? [],
                traceStatus: trace ? "loaded" : "unavailable",
              },
            ];
          }
          return prev;
        });
      } catch (err) {
        const errorText =
          err instanceof Error
            ? err.message
            : "An unexpected error occurred. Please try again.";

        // Check for 404 → session expired, regenerate
        if (err instanceof ApiError && err.status === 404) {
          const newId = uid();
          setSessionId(newId);
          try {
            localStorage.setItem(SESSION_KEY, newId);
          } catch {
            /* storage unavailable */
          }

          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              role: "assistant",
              text: "Session expired. A new session has been created. Please try your message again.",
              isError: true,
            },
          ]);
        } else if (err instanceof ApiError && err.status === 429) {
          // Rate limit — show a fixed, friendly message instead of the raw
          // provider error, regardless of the backend detail string.
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              role: "assistant",
              text: "The service is receiving too many requests right now. Please wait a few seconds and try again.",
              isError: true,
            },
          ]);
        } else {
          // General error — show inline error bubble
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              role: "assistant",
              text: errorText,
              isError: true,
            },
          ]);
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, messages],
  );

  // ── Analytics snapshot (derived from all messages) ──
  const snapshot = useMemo(() => buildSnapshot(messages), [messages]);

  // ── Render ──
  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line-soft bg-bg/90 px-4 py-3 backdrop-blur-sm sm:px-6">
        <div className="flex items-center gap-3">
          <div className="leading-tight">
            <h1 className="text-[15px] font-semibold tracking-tight text-fg">
              Soccer Analytics Agent
            </h1>
            <p className="font-mono text-[10.5px] tracking-wide text-fg-faint">
              Gemini ({geminiModel}) · Postgres + pgvector · 49K matches
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <HealthPill status={healthStatus} />
          <button
            type="button"
            onClick={() => {
              const newId = uid();
              setSessionId(newId);
              setMessages([]);
              try {
                localStorage.setItem(SESSION_KEY, newId);
              } catch {
                /* storage unavailable */
              }
            }}
            disabled={busy}
            className="rounded-lg border border-line-soft bg-surface px-3 py-1.5 text-[12px] text-fg-dim transition-colors hover:border-accent hover:text-fg disabled:opacity-40"
          >
            New Chat
          </button>
        </div>
      </header>

      {/* Split layout: conversation + analytics panel */}
      <main className="mx-auto grid w-full max-w-[1400px] flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px]">
        <ChatColumn messages={messages} busy={busy} onSend={handleSend} />
        <aside className="hidden border-l border-line-soft bg-surface/30 lg:block">
          <div className="sticky top-[57px] h-[calc(100vh-57px)] p-5">
            <AnalyticsPanel snapshot={snapshot} />
          </div>
        </aside>
      </main>
    </div>
  );
}
