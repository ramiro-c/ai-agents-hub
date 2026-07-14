import type { EloResult } from "../../lib/types";
import { num2 } from "../../lib/format";

interface Props {
  data: EloResult;
}

export function EloGauges({ data }: Props) {
  const { elos } = data;
  const entries = Object.entries(elos);

  if (entries.length === 0) {
    return <p className="text-[12px] text-fg-dim">No Elo data available.</p>;
  }

  return (
    <div className="grid gap-2">
      {entries.map(([team, entry]) => {
        // Elo values range roughly 800-2200; normalize to 0-1 for bar width
        const pct = Math.min(1, Math.max(0, (entry.elo - 800) / 1400));

        return (
          <div key={team} className="space-y-1">
            <div className="flex items-center justify-between text-[12px]">
              <span className="font-medium text-fg">{team}</span>
              <span className="font-mono tabular-nums text-fg-dim">
                {num2(entry.elo)}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-accent transition-all duration-500"
                style={{ width: `${pct * 100}%` }}
              />
            </div>
            <p className="font-mono text-[10.5px] text-fg-faint">
              {entry.matches_played} matches played
            </p>
          </div>
        );
      })}
    </div>
  );
}
