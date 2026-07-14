import type { PredictResult } from "../../lib/types";
import { pct } from "../../lib/format";

interface Props {
  data: PredictResult;
  variant: "inline" | "hero";
}

export function ProbabilityBar({ data, variant }: Props) {
  const { team1, team2, probabilities } = data;
  // Backend uses actual team names as keys (e.g. Argentina_win, Brazil_win)
  const team1Win = probabilities[`${team1}_win`] ?? 0;
  const team2Win = probabilities[`${team2}_win`] ?? 0;
  const draw = probabilities.draw ?? 0;

  const isHero = variant === "hero";

  return (
    <div className={`space-y-2 ${isHero ? "p-3" : ""}`}>
      {isHero && (
        <p className="font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
          Match prediction
        </p>
      )}

      {/* Bar */}
      <div
        className={`flex overflow-hidden rounded-full ${isHero ? "h-5" : "h-4"}`}
      >
        <div
          className="bg-green-w/70 transition-all duration-300"
          style={{ width: `${team1Win * 100}%` }}
          title={`${team1}: ${pct(team1Win)}`}
        />
        <div
          className="bg-amber-d/70 transition-all duration-300"
          style={{ width: `${draw * 100}%` }}
          title={`Draw: ${pct(draw)}`}
        />
        <div
          className="bg-red-l/70 transition-all duration-300"
          style={{ width: `${team2Win * 100}%` }}
          title={`${team2}: ${pct(team2Win)}`}
        />
      </div>

      {/* Labels */}
      <div
        className={`flex justify-between font-mono tabular-nums ${isHero ? "text-[13px]" : "text-[11px]"}`}
      >
        <span className="text-fg">
          {team1} {pct(team1Win)}
        </span>
        <span className="text-fg-dim">{pct(draw)}</span>
        <span className="text-fg">
          {team2} {pct(team2Win)}
        </span>
      </div>
    </div>
  );
}
