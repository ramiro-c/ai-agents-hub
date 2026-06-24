export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

export type ChatResponse = {
  reply: string;
  userId: string;
  sessionId: string;
};

export async function sendMessage(
  message: string,
  userId: string | null,
  sessionId: string | null,
): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      userId: userId ?? undefined,
      sessionId: sessionId ?? undefined,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : "Error al contactar con el servidor.";
    throw new Error(detail);
  }

  return response.json();
}
