import { type FormEvent, useState, useRef, useEffect, useCallback } from "react";

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
}

export function Composer({ busy, onSend }: Props) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  const trimmed = value.trim();

  // Auto-resize textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [value]);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      if (!trimmed || busy) return;
      onSend(trimmed);
      setValue("");
    },
    [trimmed, busy, onSend],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (trimmed && !busy) {
          onSend(trimmed);
          setValue("");
        }
      }
    },
    [trimmed, busy, onSend],
  );

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 border-t border-line-soft bg-surface p-3"
    >
      <textarea
        ref={taRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about matches, teams, Elo ratings…"
        disabled={busy}
        rows={1}
        className="flex-1 resize-none rounded-lg border border-line-soft bg-bg px-3 py-2 text-[14px] text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={busy || !trimmed}
        className="rounded-lg bg-accent px-4 py-2 text-[14px] font-semibold text-ink transition-colors hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "…" : "Send"}
      </button>
    </form>
  );
}
