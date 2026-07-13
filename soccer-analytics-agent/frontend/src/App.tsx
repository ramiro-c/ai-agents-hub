import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getMemory, getTrace, sendChat, type ToolCall } from "./api";

const SESSION_KEY = "soccer_agent_session_id";

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; answer: string; tools: ToolCall[] };

function randomId() {
  return crypto.randomUUID();
}

export default function App() {
  const [sessionId, setSessionId] = useState(() => {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) return stored;
    const id = randomId();
    localStorage.setItem(SESSION_KEY, id);
    return id;
  });
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memory, setMemory] = useState<{ role: string; content: string }[]>([]);
  const [trace, setTrace] = useState<
    { step: number; kind: string; content: unknown }[]
  >([]);
  const [activeTab, setActiveTab] = useState<"memory" | "trace">("memory");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function handleNewSession() {
    const id = randomId();
    localStorage.setItem(SESSION_KEY, id);
    setSessionId(id);
    setMessages([]);
    setMemory([]);
    setTrace([]);
    setError(null);
  }

  async function loadMemory() {
    try {
      const data = await getMemory(sessionId);
      setMemory(data);
    } catch {
      setMemory([]);
    }
  }

  async function loadTrace() {
    try {
      const data = await getTrace(sessionId);
      setTrace(data);
    } catch {
      setTrace([]);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [
      ...prev,
      { role: "user", text },
      { role: "assistant", answer: "", tools: [] },
    ]);
    setLoading(true);

    try {
      const response = await sendChat(text, sessionId);
      setMessages((prev) =>
        prev.slice(0, -1).concat({
          role: "assistant",
          answer: response.answer,
          tools: response.tools,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Soccer Agent</h1>
          <span className="session-id">Session: {sessionId.slice(0, 8)}…</span>
        </div>

        <button className="new-chat-btn" onClick={handleNewSession}>
          + New Chat
        </button>

        <div className="tabs">
          <button
            className={activeTab === "memory" ? "active" : ""}
            onClick={() => {
              setActiveTab("memory");
              loadMemory();
            }}
          >
            Memory
          </button>
          <button
            className={activeTab === "trace" ? "active" : ""}
            onClick={() => {
              setActiveTab("trace");
              loadTrace();
            }}
          >
            Trace
          </button>
        </div>

        <div className="panel">
          {activeTab === "memory" ? (
            memory.length === 0 ? (
              <p className="empty">No memory yet. Send a message to populate working memory.</p>
            ) : (
              <ul className="memory-list">
                {memory.map((m, i) => (
                  <li key={i}>
                    <span className={`role ${m.role}`}>{m.role}</span>
                    <span className="content">{m.content.slice(0, 100)}</span>
                  </li>
                ))}
              </ul>
            )
          ) : trace.length === 0 ? (
            <p className="empty">No trace yet.</p>
          ) : (
            <div className="trace-list">
              {trace.map((t) => (
                <div key={t.step} className="trace-step">
                  <div className="trace-head">
                    <span className="step">Step {t.step}</span>
                    <span className="kind">{t.kind}</span>
                  </div>
                  <pre>{JSON.stringify(t.content, null, 2)}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="chat">
        <header className="chat-header">
          <h2>Soccer Analytics Agent</h2>
          <p>Gemini · Postgres + pgvector · 49K matches</p>
        </header>

        <div className="messages">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Ask me about international football</h2>
              <p>
                Try: "Who won the 2022 World Cup?", "What's Argentina's Elo rating?",
                "Predict Argentina vs France", "Show me Brazil's last 5 matches"
              </p>
            </div>
          ) : (
            messages.map((msg, i) =>
              msg.role === "user" ? (
                <div key={i} className="bubble user">
                  <span className="label">You</span>
                  <p>{msg.text}</p>
                </div>
              ) : (
                <div key={i} className="bubble assistant">
                  <span className="label">Agent</span>
                  {msg.tools.length > 0 && (
                    <details className="tools-panel">
                      <summary>Tools ({msg.tools.length})</summary>
                      {msg.tools.map((t, j) => (
                        <div key={j} className="tool">
                          <code>{t.name}</code>
                          <pre className="args">{JSON.stringify(t.args, null, 2)}</pre>
                          {t.response !== undefined && (
                            <pre className="response">
                              {JSON.stringify(t.response, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </details>
                  )}
                  <div className="answer">
                    {loading && i === messages.length - 1 ? (
                      <p className="thinking">{msg.answer || "Thinking…"}</p>
                    ) : msg.answer ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.answer}
                      </ReactMarkdown>
                    ) : null}
                  </div>
                </div>
              ),
            )
          )}
          <div ref={bottomRef} />
        </div>

        {error && <div className="error">{error}</div>}

        <form className="composer" onSubmit={handleSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about matches, teams, Elo ratings..."
            disabled={loading}
            autoFocus
          />
          <button type="submit" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
