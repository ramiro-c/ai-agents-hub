import type { FormResult } from "../../lib/types";

const RESULT_COLOR: Record<string, string> = {
  W: "bg-green-w/20 text-green-w border-green-w/30",
  D: "bg-amber-d/20 text-amber-d border-amber-d/30",
  L: "bg-red-l/20 text-red-l border-red-l/30",
};

interface Props {
  data: FormResult;
}

export function FormTiles({ data }: Props) {
  const { team, form } = data;

  if (form.length === 0) {
    return (
      <p className="text-[12px] text-fg-dim">No recent matches for {team}.</p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
        {team} — last {form.length} matches
      </p>
      <div className="flex flex-wrap gap-2">
        {form.map((match, i) => (
          <div
            key={i}
            className={`flex min-w-[80px] flex-col items-center rounded-lg border px-2.5 py-1.5 font-mono text-[11px] ${RESULT_COLOR[match.result] ?? "border-line-soft text-fg-faint"}`}
            title={`${match.tournament} · ${match.date}`}
          >
            <span className="text-[13px] font-bold">{match.result}</span>
            <span className="tabular-nums">{match.score}</span>
            <span className="truncate text-[10px] opacity-70">
              {match.opponent}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
