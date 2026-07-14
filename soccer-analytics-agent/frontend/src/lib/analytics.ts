import type {
  Message,
  PredictResult,
  EloResult,
  FormResult,
  H2HResult,
  AnalyticsSnapshot,
} from "./types";

/** Distill all messages into the aggregated analytics state for the panel. */
export function buildSnapshot(messages: Message[]): AnalyticsSnapshot {
  const snapshot: AnalyticsSnapshot = {
    elos: [],
    forms: [],
    subjectTeams: [],
  };

  // Latest per single-value types, accumulated per array types
  let prediction: PredictResult | undefined;
  let h2hLatest: H2HResult | undefined;
  const teamSet = new Set<string>();

  for (const msg of messages) {
    if (msg.role !== "assistant" || !msg.trace || msg.trace.length === 0) continue;

    for (const call of msg.trace) {
      const r = call.result as Record<string, unknown>;

      switch (call.name) {
        case "predict_match": {
          const p = r as unknown as PredictResult;
          if (p.team1 && p.team2 && p.probabilities) {
            prediction = p; // latest wins
            teamSet.add(p.team1);
            teamSet.add(p.team2);
          }
          break;
        }

        case "get_team_elo": {
          const elo = r as unknown as EloResult;
          if (elo.elos) {
            snapshot.elos.push(elo);
            for (const t of Object.keys(elo.elos)) teamSet.add(t);
          }
          break;
        }

        case "get_team_form": {
          const form = r as unknown as FormResult;
          if (form.team && form.form) {
            snapshot.forms.push(form);
            teamSet.add(form.team);
          }
          break;
        }

        case "get_h2h": {
          const h2h = r as unknown as H2HResult;
          if (h2h.team1 && h2h.team2) {
            h2hLatest = h2h;
            teamSet.add(h2h.team1);
            teamSet.add(h2h.team2);
          }
          break;
        }
      }
    }
  }

  if (prediction) snapshot.prediction = prediction;
  if (h2hLatest) snapshot.h2h = h2hLatest;
  snapshot.subjectTeams = [...teamSet];

  return snapshot;
}
