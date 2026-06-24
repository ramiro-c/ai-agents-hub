import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatMessage, sendMessage } from "./api";

const USER_ID_KEY = "support_chat_user_id";
const SESSION_ID_KEY = "support_chat_session_id";

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Hola, soy Alex del equipo de soporte técnico. ¿En qué puedo ayudarte hoy?",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUserId(localStorage.getItem(USER_ID_KEY));
    setSessionId(localStorage.getItem(SESSION_ID_KEY));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    try {
      const result = await sendMessage(text, userId, sessionId);
      setUserId(result.userId);
      setSessionId(result.sessionId);
      localStorage.setItem(USER_ID_KEY, result.userId);
      localStorage.setItem(SESSION_ID_KEY, result.sessionId);
      setMessages((prev) => [...prev, { role: "assistant", text: result.reply }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Error desconocido";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleNewChat() {
    localStorage.removeItem(SESSION_ID_KEY);
    setSessionId(null);
    setMessages([
      {
        role: "assistant",
        text: "Empezamos una conversación nueva. ¿En qué puedo ayudarte?",
      },
    ]);
    setError(null);
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Soporte al Cliente</h1>
          <p>Agente ADK · Alex Chen</p>
        </div>
        <button type="button" className="secondary-btn" onClick={handleNewChat}>
          Nueva conversación
        </button>
      </header>

      <main className="chat">
        {messages.map((msg, index) => (
          <div key={index} className={`bubble ${msg.role}`}>
            <span className="label">{msg.role === "user" ? "Tú" : "Alex"}</span>
            <p>{msg.text}</p>
          </div>
        ))}
        {loading && (
          <div className="bubble assistant">
            <span className="label">Alex</span>
            <p className="typing">Escribiendo…</p>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      {error && <div className="error">{error}</div>}

      <form className="composer" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribí tu consulta…"
          disabled={loading}
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Enviar
        </button>
      </form>
    </div>
  );
}
