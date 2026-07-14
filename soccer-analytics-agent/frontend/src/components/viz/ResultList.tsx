import type { SearchResult } from "../../lib/types";

interface Props {
  data: SearchResult;
  variant: "vector" | "hybrid";
}

function snippet(text: string, maxLen = 200): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "…";
}

export function ResultList({ data, variant }: Props) {
  const { results } = data;

  if (results.length === 0) {
    return <p className="text-[12px] text-fg-dim">No matches found.</p>;
  }

  return (
    <div className="grid gap-2">
      {results.map((item) => (
        <div
          key={item.id}
          className="rounded-lg border border-line-soft bg-surface p-3"
        >
          {/* Score indicator */}
          <div className="mb-1 flex items-center justify-between">
            <span className="font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
              {variant === "hybrid" ? "Hybrid" : "Vector"} match
            </span>
            <div className="flex items-center gap-2 font-mono text-[11px] text-fg-dim">
              {variant === "hybrid" && item.vector_distance !== undefined && (
                <span title="Vector distance" className="text-fg-faint">
                  vec: {(1 - item.vector_distance).toFixed(3)}
                </span>
              )}
              {variant === "vector" && item.distance !== undefined && (
                <span
                  title="Similarity score"
                  className="text-accent"
                >
                  score: {(1 - item.distance).toFixed(3)}
                </span>
              )}
              {variant === "hybrid" && item.rank !== undefined && (
                <span
                  title="RRF rank"
                  className="text-accent"
                >
                  rank: #{item.rank}
                </span>
              )}
            </div>
          </div>

          {/* Content snippet */}
          <p className="text-[12.5px] leading-snug text-fg-dim">
            {snippet(item.content)}
          </p>
        </div>
      ))}
    </div>
  );
}
