import type { H2HResult } from "../../lib/types";

interface Props {
  data: H2HResult;
}

export function H2HRecord({ data }: Props) {
  const { team1, team2, record, total, last_matches } = data;

  const wins1 = record[team1] ?? 0;
  const wins2 = record[team2] ?? 0;
  const draws = record.draws ?? 0;

  if (!last_matches || last_matches.length === 0) {
    return (
      <p className="text-[12px] text-fg-dim">
        No head-to-head matches between {team1} and {team2}.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* W/D/L counts */}
      <div className="flex justify-center gap-3 font-mono text-[11px] text-fg-dim">
        <span className="font-medium text-fg">{team1}</span>
        <span>
          {wins1}W — {draws}D — {wins2}L
        </span>
        <span className="font-medium text-fg">{team2}</span>
      </div>

      {/* Summary bar */}
      {total > 0 && (
        <div className="flex h-5 overflow-hidden rounded-full">
          <div
            className="bg-green-w/70"
            style={{ width: `${(wins1 / total) * 100}%` }}
          />
          <div
            className="bg-amber-d/70"
            style={{ width: `${(draws / total) * 100}%` }}
          />
          <div
            className="bg-red-l/70"
            style={{ width: `${(wins2 / total) * 100}%` }}
          />
        </div>
      )}

      {/* Recent matches (last 5) */}
      <div className="space-y-1">
        <p className="font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
          Recent ({total} total)
        </p>
        {last_matches.slice(0, 5).map((m, i) => (
          <div
            key={i}
            className="flex items-center justify-between rounded border border-line-soft px-2.5 py-1.5 font-mono text-[11px]"
          >
            <span className="text-fg-dim">{m.date}</span>
            <span className="tabular-nums text-fg">
              {m.home} {m.score} {m.away}
            </span>
            <span className="text-fg-faint">{m.tournament}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
