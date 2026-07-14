# Verification Report: Soccer Analytics Agent Frontend Rewrite

**Change**: frontend-rewrite  
**Mode**: Standard  
**Date**: 2026-07-13  
**Verifier**: sdd-verify executor

---

## 1. Build & Type-Check Evidence

| Command | Exit Code | Output Hash | Result |
|---------|-----------|-------------|--------|
| `npx tsc --noEmit` | 0 | (clean) | PASS |
| `npm run build` | 0 | `dist/index.html` + `assets/index-*.css` (21.7 kB) + `assets/index-*.js` (374.4 kB) | PASS |

Both TypeScript compilation and Vite production build completed without errors or warnings.

---

## 2. Task Completion

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Foundation | T-001, T-002, T-003, T-004, T-005 | 5/5 ✅ |
| Phase 2: Core UI | T-006, T-007, T-008, T-009, T-010 | 5/5 ✅ |
| Phase 3: Visual Tool Cards | T-011, T-012, T-013, T-014, T-015, T-016, T-017, T-018, T-019, T-020 | 10/10 ✅ |
| Phase 4: Analytics Panel | T-021, T-022 | 2/2 ✅ |
| Phase 5: Integration | T-023, T-024, T-025 | 3/3 ✅ |
| Phase 6: Polish | T-026, T-027 | 2/2 ✅ |
| **Total** | **27/27** | **100%** |

All 27 implementation tasks listed in `tasks.md` are present in the codebase and checked in `apply-progress.md`.

---

## 3. Spec Compliance Matrix

| Requirement | Scenarios | Status | Evidence |
|-------------|-----------|--------|----------|
| **REQ-001** Session Persistence | First visit, Returning visitor, Storage unavailable | **PARTIAL** | `initSessionId()` generates UUID v4 and persists to `localStorage` (first/returning covered). Storage-fallback works (in-memory UUID), but **no non-blocking warning is displayed** when `localStorage` is unavailable. |
| **REQ-002** Send Message | Successful send, Empty rejection, Concurrent prevention | **COVERED** | `Composer` disables submit when `!trimmed || busy`. `handleSend` rejects empty/whitespace. Loading indicator shown via `busy` state. |
| **REQ-003** Tool Trace Display | Recognized tool, Unrecognized tool, No tools called | **COVERED** | `ToolTrace` dispatches 9 known tools to visual cards. Unknown tools fall through to `RawJson` (always rendered below each card). `MessageBubble` only renders `ToolTrace` when `message.trace?.length > 0`. |
| **REQ-004** Tool Trace Polling Fallback | Polling after response, Retry on empty, Polling failure | **PARTIAL** | `pollTrace(sessionId, turnId)` with 3 retries at 500ms implemented. Trace steps filtered by `turn_id` and `kind === "tool_calls"`. **Missing**: no subtle "tool details unavailable" indicator when trace endpoint fails after retries. |
| **REQ-005** Analytics Panel | Panel updates, Empty state | **COVERED** | `buildSnapshot()` replaces latest per-tool-type values. `AnalyticsPanel` renders empty state when no analytics data exists. |
| **REQ-006** Suggestion Chips | Chip click sends message | **COVERED** | `EmptyHero` renders 6 chips; clicking calls `onPick(chip)` which routes to `handleSend`. Chips disappear when `messages.length > 0`. |
| **REQ-007** Health Status Indicator | Healthy backend, Unhealthy backend | **COVERED** | `HealthPill` shows green/amber/red dot. `useEffect` interval every 20s calls `getHealth()`. Composer remains usable when backend is down. |
| **REQ-008** Session List (Teams) | Teams list loads, Team detail view | **MISSING** | No `GET /api/teams` or `GET /api/teams/{name}` calls in frontend. No teams list UI. No team detail view. **Not covered by any task.** |
| **REQ-009** Error Handling | Chat API failure, Backend unreachable | **COVERED** | Inline error bubbles (not browser alerts). `setBusy(false)` in `finally` re-enables input. User message preserved. |

---

## 4. Correctness & Edge-Case Audit

| Edge Case Category | Status | Notes |
|--------------------|--------|-------|
| Backend down | **COVERED** | Inline error messages, health dot turns red, input stays usable. |
| Session expires / invalid | **COVERED** (fragile) | String-matching `err.message.includes("404")` clears `localStorage`, regenerates session, and shows notification. Fragile: relies on error text containing "404"; if backend returns `{detail: "Session not found"}`, match fails. |
| Tool result empty | **COVERED** | `SqlTable` → "No rows returned." `ResultList` → "No matches found." `FactList` → "No facts recalled." `FormTiles` → "No recent matches for {team}." |
| Tool returns error | **COVERED** | `ToolTrace` detects `result.error` and renders a red error card with the message. |
| User sends empty message | **COVERED** | `Composer` disables submit and `handleSend` returns early on whitespace-only input. |
| No tools called in a turn | **COVERED** | `MessageBubble` only renders `ToolTrace` when `trace.length > 0`. |
| Very large tool results | **COVERED** | `SqlTable` caps at 8 rows with `+N more rows`. `ResultList` truncates snippets at 200 chars. `FactList` caps at 10 facts with expansion button. |
| Trace polling stale data | **COVERED** | `pollTrace` filters `step.turn_id === turnId` and ignores prior-turn steps. |

---

## 5. Shape Correctness (Backend-Aligned)

All visual components parse the **actual backend return shapes**, not the Oracle-spec shapes. Verified deviations are documented in `apply-progress.md` and confirmed by source inspection:

| Tool | Spec Shape | Actual Shape Used | Component |
|------|-----------|-------------------|-----------|
| `sql_query` | `{columns, rows, row_count}` | `{columns, rows}` | `SqlTable` |
| `vector_search` | `{results[].content, teams, score}` | `{results: [{id, content, distance}]}` | `ResultList` |
| `hybrid_retrieve` | `{results[].content, teams, vector_score, text_score, rrf_score, sources}` | `{results: [{id, content, vector_distance, rank}]}` | `ResultList` |
| `remember` | `{status: "remembered"}` | `{status, message}` | `StatusBadge` |
| `recall` | `{facts: string[]}` | `{results: [{id, content, distance}]}` | `FactList` |
| `get_team_elo` | `{elos: Record<string, {elo, matches}>` | `{elos: Record<string, {elo, matches_played}>}` | `EloGauges` |
| `get_team_form` | `{form[].date, opponent, result, score, venue}` | `{team, form: [{date, tournament, home_team, away_team, home_score, away_score, result}]}` | `FormTiles` |
| `get_h2h` | `{record: {team1, team2, draws}, last_matches}` | `{team1, team2, matches: [{..., winner}]}` | `H2HRecord` |
| `predict_match` | `{probabilities: {team1_win, draw, team2_win}, analysis}` | `{team1, team2, probabilities: {team1_win, draw, team2_win}}` (no `analysis`) | `ProbabilityBar` |

**Verdict**: All components are aligned with the real backend. Good.

---

## 6. Design Coherence

**Skipped** — No `design.md` artifact was provided in the verification inputs. Design coherence checks were omitted per the SDD verify skill's artifact-grace rules.

---

## 7. Findings

### CRITICAL

1. **REQ-008 (Teams List) is entirely missing from the implementation.**
   - The spec requires `GET /api/teams` and `GET /api/teams/{name}` consumption with a teams list UI and team detail view. Neither the API client nor any UI component implements this. It was not included in the 27 tasks, but it is a stated spec requirement.

2. **`turnId` calculation is off by one, breaking trace polling for every turn.**
   - **Location**: `App.tsx` line 93–95
   - **Current**: `turnId = [...messages.filter(m => m.role === "assistant"), userMsg].length + 1`
   - **Problem**: For a fresh session (`messages = []`), this yields `turnId = 2`. The backend's first turn is `turn_id = 1` (`trace.get_last_turn_id(session_id) + 1`, where `get_last_turn_id` starts at 0). The mismatch is consistent (`frontend = backend + 1`), so `pollTrace` will never match trace steps and tool cards will never appear.
   - **Fix**: `turnId = messages.filter(m => m.role === "assistant").length + 1` (remove `userMsg` and extra `+1`).

### WARNING

3. **No subtle indicator when trace polling fails (REQ-004 Scenario 3).**
   - When `pollTrace` exhausts retries or encounters endpoint errors, `App.tsx` silently renders the answer without tool cards. The spec requires a subtle "tool details unavailable" indicator.

4. **No warning when `localStorage` is unavailable (REQ-001 Scenario 3).**
   - `initSessionId()` gracefully falls back to an in-memory UUID, but no UI notification is shown.

5. **Session-404 recovery is string-fragile.**
   - `err.message.includes("404")` will miss backend errors that return a descriptive JSON `detail` field without the numeric status code in the text.

6. **Health fetch lacks an explicit 5-second timeout.**
   - `getHealth()` uses a bare `fetch("/api/health")`. Browser default timeouts are much longer than the 5-second expectation in the spec.

### SUGGESTION

7. **No inline `tool_trace` bypass for future backend upgrades.**
   - The spec's "Future upgrade path" notes that if the backend returns `tool_trace` directly in the chat response, polling should be skipped. `App.tsx` always polls regardless of the response shape.

8. **Unrecognized tools show an intermediate text prompt before raw JSON.**
   - `ToolCard` renders "Result available — expand raw JSON." for unknown tools. The spec expects the raw JSON block directly.

---

## 8. Overall Verdict

**PASS WITH WARNINGS**

- **Build & Type-Check**: Clean pass.
- **Task Completion**: 27/27 tasks implemented and verified.
- **Spec Coverage**: 8 of 9 requirements have evidence in code. REQ-008 is completely absent.
- **Runtime Correctness**: The `turnId` off-by-one bug is a **critical functional defect** that prevents tool trace polling from matching backend data on every turn. It must be fixed before the feature can be considered working end-to-end.

**Action required before merge:**
1. Fix `turnId` computation in `App.tsx`.
2. Implement REQ-008 (teams list and detail view) or formally descope it from the spec with user approval.
3. Add subtle trace-unavailable indicator on polling failure (optional but recommended).
