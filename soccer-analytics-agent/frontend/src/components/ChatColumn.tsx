import { useEffect, useRef } from "react";
import type { Message } from "../lib/types";
import { MessageBubble } from "./MessageBubble";
import { Composer } from "./Composer";
import { EmptyHero } from "./EmptyHero";

interface Props {
  messages: Message[];
  busy: boolean;
  onSend: (text: string) => void;
}

export function ChatColumn({ messages, busy, onSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change or busy toggles
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {/* Scrollable message area */}
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4 sm:px-6">
        {messages.length === 0 ? (
          <EmptyHero onPick={onSend} />
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))
        )}

        {/* Loading indicator while busy, shown as a separate bubble */}
        {busy && messages.length > 0 && (
          <div className="flex flex-col items-start">
            <span className="mb-1 font-mono text-[10.5px] font-semibold uppercase tracking-wide text-fg-faint">
              Agent
            </span>
            <div className="rounded-bl-md rounded-2xl border border-line-soft bg-surface px-4 py-3">
              <span className="animate-pulse text-[14px] text-fg-dim">
                Thinking…
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Pinned composer */}
      <Composer busy={busy} onSend={onSend} />
    </section>
  );
}
