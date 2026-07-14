import { memo } from "react";
import type { ToolCall } from "../lib/types";
import { RawJson } from "./viz/RawJson";
import { SqlTable } from "./viz/SqlTable";
import { ResultList } from "./viz/ResultList";
import { StatusBadge } from "./viz/StatusBadge";
import { FactList } from "./viz/FactList";
import { EloGauges } from "./viz/EloGauges";
import { FormTiles } from "./viz/FormTiles";
import { H2HRecord } from "./viz/H2HRecord";
import { ProbabilityBar } from "./viz/ProbabilityBar";

// ── Tool icon (simple text labels, no icon library) ──

function ToolIcon({ name }: { name: string }) {
  const label = ICONS[name] ?? "⚙";
  return (
    <span className="font-mono text-[11px] text-fg-faint" aria-hidden="true">
      {label}
    </span>
  );
}

const ICONS: Record<string, string> = {
  sql_query: "DB",
  vector_search: "🔍",
  hybrid_retrieve: "🔀",
  remember: "🧠",
  recall: "📋",
  get_team_elo: "📊",
  get_team_form: "📅",
  get_h2h: "⚔",
  predict_match: "🎯",
};

// ── Arg summary ──

function argSummary(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (!entries.length) return "";
  return entries
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join("  ");
}

// ── Error check ──

function hasError(
  result: Record<string, unknown>,
): result is { error: string } {
  return Boolean(result && typeof result === "object" && "error" in result);
}

// ── Render visual ──

function renderVisual(call: ToolCall) {
  switch (call.name) {
    case "sql_query":
      return <SqlTable data={call.result as unknown as Parameters<typeof SqlTable>[0]["data"]} />;
    case "vector_search":
      return <ResultList data={call.result as unknown as Parameters<typeof ResultList>[0]["data"]} variant="vector" />;
    case "hybrid_retrieve":
      return <ResultList data={call.result as unknown as Parameters<typeof ResultList>[0]["data"]} variant="hybrid" />;
    case "remember":
      return <StatusBadge status={String((call.result as Record<string,unknown>).status ?? "")} message={String((call.result as Record<string,unknown>).message ?? "")} />;
    case "recall":
      return <FactList data={call.result as unknown as Parameters<typeof FactList>[0]["data"]} />;
    case "get_team_elo":
      return <EloGauges data={call.result as unknown as Parameters<typeof EloGauges>[0]["data"]} />;
    case "get_team_form":
      return <FormTiles data={call.result as unknown as Parameters<typeof FormTiles>[0]["data"]} />;
    case "get_h2h":
      return <H2HRecord data={call.result as unknown as Parameters<typeof H2HRecord>[0]["data"]} />;
    case "predict_match":
      return <ProbabilityBar data={call.result as unknown as Parameters<typeof ProbabilityBar>[0]["data"]} variant="inline" />;
    default:
      return null;
  }
}

// ── Single tool card ──

function ToolCard({ call }: { call: ToolCall }) {
  const err = hasError(call.result);
  const visual = renderVisual(call);

  return (
    <div className="rounded-xl border border-line-soft bg-surface p-3">
      {/* Header */}
      <div className="mb-2 flex items-center gap-2">
        <ToolIcon name={call.name} />
        <span className="font-mono text-[12px] font-medium text-fg">
          {call.name}
        </span>
        {argSummary(call.args) && (
          <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-fg-faint">
            {argSummary(call.args)}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="ml-1 border-l-2 border-line-soft pl-3">
        {err ? (
          <p className="rounded-lg border border-rose/40 bg-rose/10 px-3 py-2 font-mono text-[11.5px] text-rose">
            {String(call.result.error)}
          </p>
        ) : visual ? (
          visual
        ) : (
          <p className="font-mono text-[11px] text-fg-dim">
            Result available — expand raw JSON.
          </p>
        )}
      </div>

      {/* Raw JSON fallback (always present, collapsed by default) */}
      <RawJson data={call.result} />
    </div>
  );
}

// ── Stack ──

interface Props {
  trace: ToolCall[];
}

function ToolTraceBase({ trace }: Props) {
  if (!trace || trace.length === 0) return null;

  return (
    <div className="mt-3 grid gap-2">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-fg-faint">
        {trace.length} tool {trace.length > 1 ? "calls" : "call"}
      </div>
      {trace.map((call, i) => (
        <ToolCard key={`${call.name}-${i}`} call={call} />
      ))}
    </div>
  );
}

export const ToolTrace = memo(ToolTraceBase);
