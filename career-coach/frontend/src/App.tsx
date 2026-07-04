import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  deleteSession,
  getSessionHistory,
  listSessions,
  sendChat,
  type SessionSummary,
  type ToolCall,
} from "./api";

const USER_ID_KEY = "career_coach_user_id";

type AssistantMsg = {
  role: "assistant";
  answer: string;
  thoughts: string;
  tools: ToolCall[];
};

type UserMsg = { role: "user"; text: string };
type Msg = UserMsg | AssistantMsg;

function normalizeEmail(value: string) {
  return value.trim().toLowerCase();
}

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : "Error desconocido";
}

export default function App() {
  const [emailInput, setEmailInput] = useState("");
  const [userId, setUserId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const viewIdRef = useRef(0);
  const userIdRef = useRef<string | null>(null);

  useEffect(() => {
    const storedUserId = localStorage.getItem(USER_ID_KEY);
    if (storedUserId) {
      setUserId(storedUserId);
      setEmailInput(storedUserId);
    }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    userIdRef.current = userId;
    if (!userId) {
      setSessions([]);
      setSelectedSessionId(null);
      setMessages([]);
      return;
    }

    let alive = true;
    setLoadingSessions(true);
    setError(null);

    listSessions(userId)
      .then((items) => {
        if (!alive) return;
        setSessions(items);
      })
      .catch((err) => {
        if (!alive) return;
        setError(errorMessage(err));
      })
      .finally(() => {
        if (alive) setLoadingSessions(false);
      });

    return () => {
      alive = false;
    };
  }, [userId]);

  async function refreshSessions(currentUserId: string) {
    const items = await listSessions(currentUserId);
    setSessions(items);
  }

  async function handleLoginSubmit(event: FormEvent) {
    event.preventDefault();
    const normalized = normalizeEmail(emailInput);
    if (!isValidEmail(normalized)) {
      setError("Ingresá un email valido.");
      return;
    }

    viewIdRef.current += 1;
    localStorage.setItem(USER_ID_KEY, normalized);
    setUserId(normalized);
    setEmailInput(normalized);
    setSelectedSessionId(null);
    setMessages([]);
    setError(null);
  }

  function handleLogout() {
    viewIdRef.current += 1;
    localStorage.removeItem(USER_ID_KEY);
    setUserId(null);
    setEmailInput("");
    setSessions([]);
    setSelectedSessionId(null);
    setMessages([]);
    setInput("");
    setError(null);
  }

  function handleNewChat() {
    viewIdRef.current += 1;
    setSelectedSessionId(null);
    setMessages([]);
    setError(null);
  }

  async function openSession(sessionId: string) {
    if (!userId) return;
    viewIdRef.current += 1;
    setLoadingSessions(true);
    setError(null);
    try {
      const history = await getSessionHistory(userId, sessionId);
      setSelectedSessionId(history.sessionId);
      setMessages(history.messages);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingSessions(false);
    }
  }

  async function removeSession(sessionId: string) {
    if (!userId) return;
    if (!window.confirm("Borrar esta sesion?")) return;

    const isActive = selectedSessionId === sessionId;
    if (isActive) {
      viewIdRef.current += 1;
    }

    setLoadingSessions(true);
    setError(null);
    try {
      await deleteSession(userId, sessionId);
      if (isActive) {
        setSelectedSessionId(null);
        setMessages([]);
      }
      await refreshSessions(userId);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingSessions(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || loading || !userId) return;

    setInput("");
    setError(null);
    setMessages((prev) => [
      ...prev,
      { role: "user", text },
      { role: "assistant", answer: "", thoughts: "", tools: [] },
    ]);
    setLoading(true);

    const myViewId = viewIdRef.current;
    try {
      const response = await sendChat(text, userId, selectedSessionId);
      if (viewIdRef.current !== myViewId) {
        if (userIdRef.current === userId) {
          await refreshSessions(userId);
        }
        return;
      }
      setSelectedSessionId(response.sessionId);
      setMessages((prev) =>
        prev.slice(0, -1).concat({
          role: "assistant",
          answer: response.answer,
          thoughts: response.thoughts,
          tools: response.tools,
        }),
      );
      await refreshSessions(userId);
    } catch (err) {
      if (viewIdRef.current === myViewId) {
        setError(errorMessage(err));
      }
    } finally {
      setLoading(false);
    }
  }

  if (!userId) {
    return (
      <div className="app">
        <main className="login">
          <form className="login-card" onSubmit={handleLoginSubmit}>
            <h1>Career Coach</h1>
            <p>Ingresá tu email para ver tus sesiones y seguir desde ahi.</p>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              placeholder="tu@email.com"
              autoComplete="email"
              autoFocus
            />
            <button type="submit">Entrar</button>
            {error && <div className="error">{error}</div>}
          </form>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div>
            <h1>Career Coach</h1>
            <p>{userId}</p>
          </div>
          <button type="button" className="secondary-btn" onClick={handleLogout}>
            Salir
          </button>
        </div>

        <button type="button" className="primary-btn" onClick={handleNewChat}>
          Nueva conversacion
        </button>

        <div className="sessions-panel">
          <div className="sessions-panel-header">
            <span>Sesiones</span>
            {loadingSessions && <span className="sessions-loading">Cargando...</span>}
          </div>
          <div className="sessions-list">
            {sessions.length === 0 ? (
              <p className="sessions-empty">Todavia no hay sesiones.</p>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.sessionId}
                  className={`session-item ${
                    session.sessionId === selectedSessionId ? "active" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="session-main"
                    onClick={() => openSession(session.sessionId)}
                  >
                    <strong>{session.title}</strong>
                    {session.lastUpdate && <span>{session.lastUpdate}</span>}
                  </button>
                  <button
                    type="button"
                    className="session-delete"
                    onClick={() => removeSession(session.sessionId)}
                    aria-label={`Borrar ${session.title}`}
                  >
                    Borrar
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </aside>

      <section className="chat-shell">
        <header className="header">
          <div>
            <h1>Career Coach</h1>
            <p>Agente ADK · Gemini · Vertex Agent Engine</p>
          </div>
          <div className="header-actions">
            <span className="session-badge">
              {selectedSessionId ? "Sesion activa" : "Nueva conversacion"}
            </span>
          </div>
        </header>

        <main className="chat">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Elegi una sesion o empezá una nueva</h2>
              <p>
                El historial ahora se separa por email y por sesion, asi no se mezclan
                conversaciones viejas.
              </p>
            </div>
          ) : (
            messages.map((msg, index) =>
              msg.role === "user" ? (
                <div key={index} className="bubble user">
                  <span className="label">Tu</span>
                  <p>{msg.text}</p>
                </div>
              ) : (
                <div key={index} className="bubble assistant">
                  <span className="label">Coach</span>
                  {msg.thoughts && (
                    <details
                      className="panel thoughts"
                      open={loading && index === messages.length - 1 && msg.thoughts.length > 0}
                    >
                      <summary>Pensamiento</summary>
                      <pre>{msg.thoughts}</pre>
                    </details>
                  )}
                  {msg.tools.length > 0 && (
                    <details
                      className="panel tools"
                      open={loading && index === messages.length - 1 && msg.tools.length > 0}
                    >
                      <summary>Tools ({msg.tools.length})</summary>
                      {msg.tools.map((t, i) => (
                        <div key={i} className="tool">
                          <code className="tool-name">{t.name}</code>
                          <pre className="tool-args">{JSON.stringify(t.args, null, 2)}</pre>
                          {t.response !== undefined && (
                            <pre className="tool-res">
                              {JSON.stringify(t.response, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </details>
                  )}
                  <div className="answer">
                    {loading && index === messages.length - 1 ? (
                      <p className="answer-loading">{msg.answer || "Pensando..."}</p>
                    ) : msg.answer ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.answer}</ReactMarkdown>
                    ) : null}
                  </div>
                </div>
              ),
            )
          )}
          <div ref={bottomRef} />
        </main>

        {error && <div className="error">{error}</div>}

        <form className="composer" onSubmit={handleSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ej: quiero pasar de backend a ML engineer en 9 meses, 10 hs/semana..."
            disabled={loading}
            autoFocus
          />
          <button type="submit" disabled={loading || !input.trim()}>
            Enviar
          </button>
        </form>
      </section>
    </div>
  );
}
