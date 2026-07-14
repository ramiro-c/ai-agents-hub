# Tasks: Soccer Analytics Agent Frontend Rewrite

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,750 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 4 PRs: Foundation → Core UI → Tool Cards → Integration |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|----|----------------------|-----------------|-------------------|
| 1 | Tailwind + types + API client | PR 1 | npm run dev | dev server | git checkout main -- package.json vite.config.ts src/index.css src/api.ts src/lib/ |
| 2 | Chat shell components | PR 2 | Visual render check | dev server | rm src/components/ChatColumn.tsx MessageBubble.tsx Composer.tsx EmptyHero.tsx HealthPill.tsx |
| 3 | Tool cards + dispatcher | PR 3 | Mock data render | dev server | rm -rf src/components/viz/ src/components/ToolTrace.tsx |
| 4 | Analytics + App integration | PR 4 | End-to-end chat | dev server + backend | git checkout main -- src/App.tsx |

---

## Phase 1: Foundation

### T-001 ✅
**Title**: Install Tailwind v4 and configure Vite
**Files**: `soccer-analytics-agent/frontend/package.json`, `vite.config.ts`
**Depends on**: None
**Description**: Add `@tailwindcss/vite` and `tailwindcss` dev deps. Import tailwindcss plugin in `vite.config.ts` and add to plugins array.
**Verification**: `npm run dev` starts without errors.
**Estimated lines**: ~8 changed

### T-002 ✅
**Title**: Replace index.css with Tailwind v4 theme
**Files**: `soccer-analytics-agent/frontend/src/index.css`
**Depends on**: T-001
**Description**: Delete all BEM CSS. Replace with `@import "tailwindcss"` and `@theme` block with dark theme tokens (bg, surface, accent, text colors).
**Verification**: UI renders with Tailwind utility classes; no remaining custom CSS selectors.
**Estimated lines**: ~448 changed (del 388, add ~60)

### T-003 ✅
**Title**: Create shared TypeScript types
**Files**: `soccer-analytics-agent/frontend/src/lib/types.ts`
**Depends on**: None
**Description**: Define `Message`, `ToolCall`, `ChatResponse`, `TraceResponse`, `TraceStep`, and all viz-specific types (`SqlResult`, `SearchResult`, `EloResult`, `FormResult`, `H2HResult`, `PredictResult`, `AnalyticsSnapshot`).
**Verification**: File compiles with `tsc --noEmit`.
**Estimated lines**: ~100 new

### T-004 ✅
**Title**: Create format helpers
**Files**: `soccer-analytics-agent/frontend/src/lib/format.ts`
**Depends on**: T-003
**Description**: Export `pct(n)` for percentage formatting, `signed(n)` for +/- numbers, `num2(n)` for 2-decimal numbers.
**Verification**: Helpers return correct strings for sample inputs.
**Estimated lines**: ~30 new

### T-005 ✅
**Title**: Rewrite API client with trace polling
**Files**: `soccer-analytics-agent/frontend/src/api.ts`
**Depends on**: T-003
**Description**: Replace old `sendChat`, `getMemory`, `getTrace` with typed fetch to our actual endpoints. Add `getHealth()`, `getTrace(sessionId)`, and `pollTrace(sessionId, turnId, retries)` with 3 retries at 500ms.
**Verification**: All functions compile; `pollTrace` resolves with trace or null after retries.
**Estimated lines**: ~120 changed (del 51, add ~80)

---

## Phase 2: Core UI

### T-006 ✅
**Title**: Create HealthPill component
**Files**: `soccer-analytics-agent/frontend/src/components/HealthPill.tsx`
**Depends on**: T-003
**Description**: Green/amber/red dot + label based on `HealthStatus`. Use Tailwind color utilities.
**Verification**: Renders correct color for each status prop.
**Estimated lines**: ~30 new

### T-007 ✅
**Title**: Create Composer component
**Files**: `soccer-analytics-agent/frontend/src/components/Composer.tsx`
**Depends on**: T-002, T-003
**Description**: Textarea + send button. Disable when `busy` or empty. Auto-resize textarea. Call `onSend(text)` on submit.
**Verification**: Empty input disables submit; sends on Enter; busy state disables controls.
**Estimated lines**: ~50 new

### T-008 ✅
**Title**: Create EmptyHero component
**Files**: `soccer-analytics-agent/frontend/src/components/EmptyHero.tsx`
**Depends on**: T-002
**Description**: Render suggestion chips when conversation empty. Clicking a chip calls `onPick(q)` with the chip text.
**Verification**: Chips visible when no messages; click triggers callback.
**Estimated lines**: ~40 new

### T-009 ✅
**Title**: Create MessageBubble component
**Files**: `soccer-analytics-agent/frontend/src/components/MessageBubble.tsx`
**Depends on**: T-002, T-003, T-020
**Description**: Render user or assistant bubble. Assistant bubble shows markdown via `react-markdown` + `remark-gfm`, plus `ToolTrace` when `message.trace` exists.
**Verification**: User bubble right-aligned; assistant renders markdown tables; shows ToolTrace when trace present.
**Estimated lines**: ~60 new

### T-010 ✅
**Title**: Create ChatColumn component
**Files**: `soccer-analytics-agent/frontend/src/components/ChatColumn.tsx`
**Depends on**: T-007, T-008, T-009
**Description**: Scrollable message list with `MessageBubble`s. Pin `Composer` to bottom. Show `EmptyHero` when `messages.length === 0`. Auto-scroll to bottom on new messages.
**Verification**: Scrolls to bottom; empty state shows chips; composer pinned.
**Estimated lines**: ~40 new

---

## Phase 3: Visual Tool Cards

### T-011 ✅
**Title**: Create RawJson fallback component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/RawJson.tsx`
**Depends on**: T-002
**Description**: Collapsible `<details>` block showing raw JSON. Default collapsed. Used for unrecognized tools.
**Verification**: Clicking summary expands JSON; collapses on second click.
**Estimated lines**: ~40 new

### T-012 ✅
**Title**: Create SqlTable component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/SqlTable.tsx`
**Depends on**: T-002, T-003
**Description**: HTML table from `SqlResult`. Cap at 8 rows with `+N more rows` footer. Handle `row_count === 0` with "No results" message.
**Verification**: Renders headers and rows; caps at 8; shows empty state.
**Estimated lines**: ~60 new

### T-013 ✅
**Title**: Create ResultList component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/ResultList.tsx`
**Depends on**: T-002, T-003
**Description**: Stacked cards for `vector_search` and `hybrid_retrieve`. Each card shows truncated snippet (~200 chars), team badges, score indicator. Hybrid variant shows source badges and RRF score.
**Verification**: Vector cards show score; hybrid cards show RRF + source badges; truncates long snippets.
**Estimated lines**: ~70 new

### T-014 ✅
**Title**: Create StatusBadge component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/StatusBadge.tsx`
**Depends on**: T-002
**Description**: Green pill "Remembered" for `remember` tool. No additional data display.
**Verification**: Renders green confirmation pill with correct text.
**Estimated lines**: ~20 new

### T-015 ✅
**Title**: Create FactList component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/FactList.tsx`
**Depends on**: T-002, T-003
**Description**: Numbered list for `recall` facts. Handle empty `facts[]` with "No facts recalled". Cap at 10 with "show more" expansion.
**Verification**: Renders numbered facts; shows empty state; caps at 10.
**Estimated lines**: ~30 new

### T-016 ✅
**Title**: Create EloGauges component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/EloGauges.tsx`
**Depends on**: T-002, T-003, T-004
**Description**: Per-team Elo value + match count. Use `num2()` for formatting. Handle `not_found` teams.
**Verification**: Shows team name, Elo numeric, and matches count.
**Estimated lines**: ~50 new

### T-017 ✅
**Title**: Create FormTiles component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/FormTiles.tsx`
**Depends on**: T-002, T-003
**Description**: Horizontal row of W/D/L tiles. Color-code: green W, amber D, red L. Show score and opponent per tile. Handle empty `form[]`.
**Verification**: Tiles color-coded correctly; shows empty state.
**Estimated lines**: ~60 new

### T-018 ✅
**Title**: Create H2HRecord component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/H2HRecord.tsx`
**Depends on**: T-002, T-003
**Description**: Summary bar (W/D/L counts) + list of recent match results. Show team names from `team1`/`team2`.
**Verification**: Summary bar counts match; recent matches listed with dates and scores.
**Estimated lines**: ~70 new

### T-019 ✅
**Title**: Create ProbabilityBar component
**Files**: `soccer-analytics-agent/frontend/src/components/viz/ProbabilityBar.tsx`
**Depends on**: T-002, T-003, T-004
**Description**: 3-segment horizontal bar (team1_win / draw / team2_win) with percentages. Support `variant: "inline"` (in message) and `variant: "hero"` (in analytics panel, larger).
**Verification**: Segments sum to 100%; percentages formatted with `pct()`; both variants render.
**Estimated lines**: ~50 new

### T-020 ✅
**Title**: Create ToolTrace dispatcher
**Files**: `soccer-analytics-agent/frontend/src/components/ToolTrace.tsx`
**Depends on**: T-011, T-012, T-013, T-014, T-015, T-016, T-017, T-018, T-019
**Description**: Map `call.name` to viz component. Handle errors (`result.error` → error card). Fall back to `RawJson` for unknown tools. Render tool icon + arg summary in header.
**Verification**: Each known tool renders correct card; unknown tool → RawJson; error → error card.
**Estimated lines**: ~80 new

---

## Phase 4: Analytics Panel

### T-021 ✅
**Title**: Create analytics snapshot builder
**Files**: `soccer-analytics-agent/frontend/src/lib/analytics.ts`
**Depends on**: T-003
**Description**: `buildSnapshot(messages)` scans all messages for `predict_match`, `get_team_elo`, `get_team_form`, `get_h2h` results. Returns latest value per tool type + `subjectTeams` deduplicated list.
**Verification**: Snapshot updates when new analytics message arrives; replaces old values for same tool type.
**Estimated lines**: ~80 new

### T-022 ✅
**Title**: Create AnalyticsPanel component
**Files**: `soccer-analytics-agent/frontend/src/components/AnalyticsPanel.tsx`
**Depends on**: T-016, T-017, T-018, T-019, T-021
**Description**: Right sidebar showing `ProbabilityBar` (hero), `EloGauges`, `FormTiles`, `H2HRecord` from snapshot. Show empty state when no data.
**Verification**: Panel updates after prediction; empty state when no analytics.
**Estimated lines**: ~60 new

---

## Phase 5: Integration

### T-023 ✅
**Title**: Rewrite App.tsx with split layout
**Files**: `soccer-analytics-agent/frontend/src/App.tsx`
**Depends on**: T-005, T-006, T-010, T-022
**Description**: Replace monolith with split layout: `HealthPill` in header, `ChatColumn` left, `AnalyticsPanel` right. Manage `sessionId` (localStorage), `messages`, `busy`, `healthStatus`, `teams` state.
**Verification**: Layout renders two columns; session persists across reload.
**Estimated lines**: ~500 changed (del 238, add ~250)

### T-024 ✅
**Title**: Implement trace polling with retries
**Files**: `soccer-analytics-agent/frontend/src/App.tsx`
**Depends on**: T-005, T-020
**Description**: After `sendChat` response, call `pollTrace(sessionId, turnId)`. Match steps by `turn_id`. Merge tool calls into assistant message via `setMessages`. If `tool_trace` exists in chat response, skip polling.
**Verification**: Tool cards appear after answer; retries work; skips polling when backend returns trace inline.
**Estimated lines**: ~60 changed (within App.tsx)

### T-025 ✅
**Title**: Implement health polling
**Files**: `soccer-analytics-agent/frontend/src/App.tsx`
**Depends on**: T-023
**Description**: `useEffect` interval every 20s calling `getHealth()`. Update `healthStatus`. Timeout after 5s.
**Verification**: Health dot turns green when backend up, red when down.
**Estimated lines**: ~30 changed (within App.tsx)

---

## Phase 6: Polish

### T-026 ✅
**Title**: Add error handling and edge cases
**Files**: `soccer-analytics-agent/frontend/src/App.tsx`
**Depends on**: T-023, T-024
**Description**: Handle `POST /api/chat` errors (inline message, not alert). Handle 404 session → clear localStorage, regenerate, notify. Handle empty input rejection. Handle trace endpoint errors with subtle indicator.
**Verification**: Backend down shows error bubble; 404 resets session; empty input rejected.
**Estimated lines**: ~80 changed (within App.tsx)

### T-027 ✅
**Title**: Clean up old files and verify build
**Files**: `soccer-analytics-agent/frontend/src/App.tsx` (final cleanup)
**Depends on**: All prior tasks
**Description**: Delete any remaining BEM CSS classes. Ensure no unused imports. Verify `npm run dev` and `npm run build` pass. Confirm no compiler warnings.
**Verification**: `npm run build` exits 0; `npm run dev` renders correctly; no TypeScript errors.
**Estimated lines**: ~20 changed
