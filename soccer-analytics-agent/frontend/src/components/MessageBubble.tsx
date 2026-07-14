import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../lib/types";
import { ToolTrace } from "./ToolTrace";

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
    >
      {/* Label */}
      <span className="mb-1 font-mono text-[10.5px] font-semibold uppercase tracking-wide text-fg-faint">
        {isUser ? "You" : "Agent"}
      </span>

      {/* Bubble */}
      <div
        className={`min-w-0 max-w-[85%] rounded-2xl px-4 py-3 text-[14px] leading-relaxed ${
          isUser
            ? "rounded-br-md bg-accent/20 text-fg"
            : message.isError
              ? "rounded-bl-md border border-rose/40 bg-rose/10 text-rose"
              : "rounded-bl-md border border-line-soft bg-surface text-fg"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.text}</p>
        ) : (
          <>
            {/* Markdown answer */}
            <div className="prose prose-invert prose-sm max-w-none [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-line-soft [&_th]:px-2 [&_th]:py-1 [&_th]:text-[12px] [&_td]:border [&_td]:border-line-soft [&_td]:px-2 [&_td]:py-1 [&_td]:text-[12px] [&_code]:rounded [&_code]:bg-surface-2 [&_code]:px-1 [&_code]:text-[12px] [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-surface-2 [&_pre]:p-3 [&_pre]:text-[12px]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.text || (message.isError ? "" : "…")}
              </ReactMarkdown>
            </div>

            {/* Tool trace cards */}
            {message.trace && message.trace.length > 0 && (
              <ToolTrace trace={message.trace} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
