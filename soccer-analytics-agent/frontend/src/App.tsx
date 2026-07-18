import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HealthPill } from "./components/HealthPill";
import { ChatColumn } from "./components/ChatColumn";
import { AnalyticsPanel } from "./components/AnalyticsPanel";
import { buildSnapshot } from "./lib/analytics";
import { sendChatStream, getHealth } from "./api";
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
  const streamAbortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight stream on unmount
  useEffect(() => {
    return () => streamAbortRef.current?.abort();
  }, []);

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
      const assistantId = nextId();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        text: "",
        trace: [],
      };

      // Optimistic: show the user message and an empty assistant message
      // immediately so tool calls / deltas can populate live.
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setBusy(true);

      // Cancel any previous in-flight stream before starting a new one.
      streamAbortRef.current?.abort();
      const ctrl = new AbortController();
      streamAbortRef.current = ctrl;

      function updateAssistant(updater: (msg: Message) => Message) {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? updater(m) : m)),
        );
      }

      try {
        await sendChatStream(
          trimmed,
          sid,
          {
            onToolCall: (calls) => {
              updateAssistant((m) => ({
                ...m,
                trace: [...(m.trace ?? []), ...calls],
              }));
            },
            onDelta: (text) => {
              updateAssistant((m) => ({ ...m, text: m.text + text }));
            },
            onDone: (ev) => {
              if (ev.session_id && ev.session_id !== sessionRef.current) {
                setSessionId(ev.session_id);
                try {
                  localStorage.setItem(SESSION_KEY, ev.session_id);
                } catch {
                  /* storage unavailable */
                }
              }
              updateAssistant((m) => ({
                ...m,
                text: ev.answer || m.text,
                traceStatus: "loaded",
              }));
            },
            onError: (ev) => {
              if (ev.status === 404) {
                // Session expired — regenerate.
                const newId = uid();
                setSessionId(newId);
                try {
                  localStorage.setItem(SESSION_KEY, newId);
                } catch {
                  /* storage unavailable */
                }
                updateAssistant((m) => ({
                  ...m,
                  text: "Session expired. A new session has been created. Please try your message again.",
                  isError: true,
                }));
              } else if (ev.status === 429) {
                // Rate limit — show a fixed, friendly message instead of the
                // raw provider error, regardless of the backend detail string.
                updateAssistant((m) => ({
                  ...m,
                  text: "The service is receiving too many requests right now. Please wait a few seconds and try again.",
                  isError: true,
                }));
              } else {
                updateAssistant((m) => ({
                  ...m,
                  text: ev.detail || `Error ${ev.status}`,
                  isError: true,
                }));
              }
            },
          },
          ctrl.signal,
        );
      } catch (err) {
        const errorText =
          err instanceof Error
            ? err.message
            : "An unexpected error occurred. Please try again.";
        updateAssistant((m) => ({ ...m, text: errorText, isError: true }));
      } finally {
        if (streamAbortRef.current === ctrl) {
          streamAbortRef.current = null;
        }
        setBusy(false);
      }
    },
    [busy],
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
