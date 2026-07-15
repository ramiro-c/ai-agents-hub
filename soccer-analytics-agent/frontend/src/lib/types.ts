// ── Backend contract shapes ──

/** POST /api/chat response */
export interface ChatResponse {
  session_id: string;
  answer: string;
  /** Server-authoritative turn id — use this to fetch this turn's trace. */
  turn_id: number;
}

/** GET /api/sessions/{id}/trace response */
export interface TraceResponse {
  session_id: string;
  trace: TraceStep[];
}

export interface TraceStep {
  turn_id: number;
  step: number;
  content: TraceContent;
}

export type TraceContent =
  | { kind: "answer"; text: string }
  | { kind: "tool_calls"; calls: RawToolCall[] };

export interface RawToolCall {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

// ── App-internal types (parsed from backend shapes) ──

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  text: string;
  trace?: ToolCall[];
  traceStatus?: "loading" | "loaded" | "unavailable";
  isError?: boolean;
}

// ── Viz-specific result shapes (matched to our actual backend returns) ──

export interface SqlResult {
  columns: string[];
  rows: (string | number | null)[][];
}

export interface SearchResultItem {
  id: number;
  content: string;
  distance?: number; // vector_search
  vector_distance?: number; // hybrid_retrieve
  rank?: number; // hybrid_retrieve
}

export interface SearchResult {
  results: SearchResultItem[];
}

export interface EloEntry {
  elo: number;
  matches_played: number;
}

export interface EloResult {
  elos: Record<string, EloEntry>;
  not_found?: string[] | null;
}

export interface FormMatch {
  date: string;
  opponent: string;
  result: "W" | "D" | "L";
  score: string; // "4-1"
  venue: "home" | "away";
  tournament: string;
}

export interface FormResult {
  team: string;
  form: FormMatch[];
  last_n: number;
}

export interface H2HMatch {
  date: string;
  home: string;
  away: string;
  score: string; // "4-1"
  tournament: string;
}

export interface H2HResult {
  team1: string;
  team2: string;
  record: Record<string, number>;
  total: number;
  last_matches: H2HMatch[];
}

/** Backend returns dynamic keys like Argentina_win, Brazil_win, draw. */
export type PredictProbabilities = Record<string, number>;

export interface PredictResult {
  team1: string;
  team2: string;
  probabilities: PredictProbabilities;
}

export interface RememberResult {
  status: string;
  message: string;
}

export interface RecallResultItem {
  id: number;
  content: string;
  distance: number;
}

export interface RecallResult {
  facts: RecallResultItem[];
}

// ── Health ──

export type HealthStatus = "healthy" | "unhealthy" | "connecting";

// ── Analytics aggregation ──

export interface AnalyticsSnapshot {
  prediction?: PredictResult;
  elos: EloResult[];
  forms: FormResult[];
  h2h?: H2HResult;
  subjectTeams: string[];
}
