# Apply Progress: Soccer Analytics Agent Frontend Rewrite

**Change**: frontend-rewrite
**Mode**: Standard
**Branch**: main (feat/frontend-rewrite)
**Date**: 2026-07-13

## Completed Tasks

### Phase 1: Foundation
- [x] T-001 — Installed Tailwind v4 (`@tailwindcss/vite`, `tailwindcss`) and configured Vite
- [x] T-002 — Replaced `index.css` BEM styles (~388 lines) with Tailwind `@import` + `@theme` block (~60 lines)
- [x] T-003 — Created `src/lib/types.ts` with all TypeScript interfaces adapted to actual backend shapes
- [x] T-004 — Created `src/lib/format.ts` with `pct()`, `signed()`, `num2()` helpers
- [x] T-005 — Rewrote `src/api.ts` with typed `sendChat()`, `getTrace()`, `getHealth()`, and `pollTrace()` (3 retries, 500ms)

### Phase 2: Core UI
- [x] T-006 — Created `src/components/HealthPill.tsx` with green/amber/red dot per HealthStatus
- [x] T-007 — Created `src/components/Composer.tsx` with auto-resize textarea, Enter-to-send, busy/empty disabled
- [x] T-008 — Created `src/components/EmptyHero.tsx` with 6 suggestion chips
- [x] T-009 — Created `src/components/MessageBubble.tsx` with react-markdown + ToolTrace integration
- [x] T-010 — Created `src/components/ChatColumn.tsx` with scrollable messages, pinned Composer, EmptyHero on empty

### Phase 3: Visual Tool Cards
- [x] T-011 — Created `src/components/viz/RawJson.tsx` — collapsible `<details>` JSON fallback
- [x] T-012 — Created `src/components/viz/SqlTable.tsx` — HTML table from `{columns, rows}`, capped at 8 rows, empty state
- [x] T-013 — Created `src/components/viz/ResultList.tsx` — stacked cards for vector_search and hybrid_retrieve, adapted to actual `{results: [{id, content, distance}]}` shapes
- [x] T-014 — Created `src/components/viz/StatusBadge.tsx` — green pill for `remember` tool
- [x] T-015 — Created `src/components/viz/FactList.tsx` — numbered list for `recall` results, capped at 10 with expansion
- [x] T-016 — Created `src/components/viz/EloGauges.tsx` — per-team Elo bars from `{elos: Record<string, {elo, matches_played}>}`
- [x] T-017 — Created `src/components/viz/FormTiles.tsx` — W/D/L color-coded tiles from actual `{form: [{date, tournament, home_team, away_team, home_score, away_score, result}]}` shape
- [x] T-018 — Created `src/components/viz/H2HRecord.tsx` — W/D/L summary bar + recent matches from actual `{team1, team2, matches: [{..., winner}]}` shape
- [x] T-019 — Created `src/components/viz/ProbabilityBar.tsx` — 3-segment bar from `{team1, team2, probabilities: {team1_win, draw, team2_win}}`, inline + hero variants
- [x] T-020 — Created `src/components/ToolTrace.tsx` — dispatcher mapping all 9 tool names to viz components, error cards, RawJson fallback

### Phase 4: Analytics Panel
- [x] T-021 — Created `src/lib/analytics.ts` — `buildSnapshot(messages)` scanning for predict_match, get_team_elo, get_team_form, get_h2h
- [x] T-022 — Created `src/components/AnalyticsPanel.tsx` — right sidebar with ProbabilityBar (hero), EloGauges, FormTiles, H2HRecord, subjectTeams tags, empty state

### Phase 5: Integration
- [x] T-023 — Rewrote `src/App.tsx` — split layout (HealthPill header, ChatColumn left, AnalyticsPanel right), localStorage sessionId, state management
- [x] T-024 — Implemented trace polling: after sendChat, pollTrace(sessionId, turnId) merges ToolCall[] into assistant message
- [x] T-025 — Implemented health polling: useEffect interval every 20s calling getHealth()

### Phase 6: Polish
- [x] T-026 — Added error handling: inline error bubbles (not alert), 404 session recovery (regenerate + notify), empty input rejection, busy-state concurrency prevention
- [x] T-027 — Verified build: `npm run build` exits 0, `npx tsc --noEmit` clean, zero compiler warnings, all BEM CSS removed

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `package.json` | Modified | Added `@tailwindcss/vite` and `tailwindcss` dev deps |
| `vite.config.ts` | Modified | Added `@tailwindcss/vite` plugin |
| `src/index.css` | Replaced | Tailwind v4 `@import` + `@theme` dark tokens (deleted ~388 lines BEM) |
| `src/api.ts` | Rewritten | Typed fetch with pollTrace (3 retries, 500ms), getHealth, getTrace |
| `src/App.tsx` | Rewritten | Split layout, session mgmt, health/trace polling, error handling |
| `src/lib/types.ts` | Created | All TS interfaces adapted to actual backend shapes |
| `src/lib/format.ts` | Created | `pct()`, `signed()`, `num2()` helpers |
| `src/lib/analytics.ts` | Created | `buildSnapshot()` message aggregator |
| `src/components/HealthPill.tsx` | Created | Status dot component |
| `src/components/Composer.tsx` | Created | Textarea + send button |
| `src/components/EmptyHero.tsx` | Created | Suggestion chips |
| `src/components/MessageBubble.tsx` | Created | Chat bubble with markdown |
| `src/components/ChatColumn.tsx` | Created | Scrollable message list |
| `src/components/ToolTrace.tsx` | Created | Tool card dispatcher |
| `src/components/AnalyticsPanel.tsx` | Created | Analytics sidebar |
| `src/components/viz/RawJson.tsx` | Created | JSON fallback |
| `src/components/viz/SqlTable.tsx` | Created | SQL result table |
| `src/components/viz/ResultList.tsx` | Created | Search result cards |
| `src/components/viz/StatusBadge.tsx` | Created | Remember pill |
| `src/components/viz/FactList.tsx` | Created | Recall fact list |
| `src/components/viz/EloGauges.tsx` | Created | Elo bars |
| `src/components/viz/FormTiles.tsx` | Created | Form W/D/L tiles |
| `src/components/viz/H2HRecord.tsx` | Created | H2H summary + matches |
| `src/components/viz/ProbabilityBar.tsx` | Created | Prediction bar |

## Deviations from Design

1. **Backend shape adaptation**: The actual backend tool shapes differ from both the spec and design docs. Every viz component was adapted to the verified backend shapes documented in the prompt:
   - `get_team_elo` returns `{elos: Record<string, {elo, matches_played}>}` (not per-team objects with multiple Elo sub-types)
   - `get_team_form` returns `{team, form: [{date, tournament, home_team, away_team, home_score, away_score, result}]}` (not `{n, form, avg_goals_scored, ...}`)
   - `get_h2h` returns `{team1, team2, matches: [{..., winner}]}` (not `{record: {team1, draws, ...}}`)
   - `recall` returns `{results: [{id, content, distance}]}` (not `{facts: string[]}`)
   - `predict_match` has no `analysis`/`prediction_note` field
   - `vector_search`/`hybrid_retrieve` have `{results: [{id, content, distance/vector_distance, rank}]}` (no `teams`, `sources`, `rrf_score` fields)

2. **No Frame Motion**: Per design decision #3, CSS transitions only. No animation library.

3. **No icon library**: Tool icons use simple text labels (DB, 🔍, 🔀, 🧠, 📋, 📊, 📅, ⚔, 🎯) instead of @phosphor-icons/react (not installed).

4. **Single PR**: Per `exception-ok` delivery strategy, all 27 tasks implemented in one batch instead of 4 chained PRs.

## Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command | `npx tsc --noEmit` — 0 errors |
| Runtime harness | `npm run build` — exit 0, outputs `dist/` (374KB JS + 22KB CSS) |
| Rollback boundary | `git checkout main -- package.json vite.config.ts src/index.css src/api.ts src/App.tsx && rm -rf src/lib/ src/components/` |

## Workload / PR Boundary
- Mode: size:exception
- Current work unit: All 27 tasks (single batch)
- Boundary: Full implementation from foundation through polish
- Review budget: ~1,750 lines estimated, 23 files total

## Status
27/27 tasks complete. Ready for verify.
