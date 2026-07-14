import type { AnalyticsSnapshot } from "../lib/types";
import { ProbabilityBar } from "./viz/ProbabilityBar";
import { EloGauges } from "./viz/EloGauges";
import { FormTiles } from "./viz/FormTiles";
import { H2HRecord } from "./viz/H2HRecord";

interface Props {
  snapshot: AnalyticsSnapshot;
}

export function AnalyticsPanel({ snapshot }: Props) {
  const hasData =
    snapshot.prediction ||
    snapshot.elos.length > 0 ||
    snapshot.forms.length > 0 ||
    snapshot.h2h;

  if (!hasData) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
          Analytics Panel
        </p>
        <p className="text-[13px] text-fg-dim">
          No analytics data yet.
        </p>
        <p className="text-[11px] text-fg-faint">
          Ask the agent to predict a match or look up team stats.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      <p className="font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
        Analytics Panel
      </p>

      {/* Subject teams */}
      {snapshot.subjectTeams.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {snapshot.subjectTeams.map((team) => (
            <span
              key={team}
              className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 font-mono text-[11px] text-accent"
            >
              {team}
            </span>
          ))}
        </div>
      )}

      {/* Prediction */}
      {snapshot.prediction && (
        <section className="rounded-xl border border-line-soft bg-surface p-3">
          <ProbabilityBar data={snapshot.prediction} variant="hero" />
        </section>
      )}

      {/* Elo */}
      {snapshot.elos.length > 0 && (
        <section>
          <p className="mb-2 font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
            Elo Ratings
          </p>
          {snapshot.elos.map((elo, i) => (
            <EloGauges key={i} data={elo} />
          ))}
        </section>
      )}

      {/* Form */}
      {snapshot.forms.length > 0 && (
        <section>
          <p className="mb-2 font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
            Recent Form
          </p>
          {snapshot.forms.map((form, i) => (
            <FormTiles key={i} data={form} />
          ))}
        </section>
      )}

      {/* H2H */}
      {snapshot.h2h && (
        <section>
          <p className="mb-2 font-mono text-[10.5px] uppercase tracking-wide text-fg-faint">
            Head-to-Head
          </p>
          <H2HRecord data={snapshot.h2h} />
        </section>
      )}
    </div>
  );
}
