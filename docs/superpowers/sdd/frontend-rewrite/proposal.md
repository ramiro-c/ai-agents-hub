# Proposal: Soccer Analytics Agent Frontend Rewrite

## Intent

Replace the bare-bones chat UI with a polished, Oracle-workshop-inspired interface that turns raw tool output into readable visual cards. The current frontend dumps JSON into `<pre>` tags, freezes when switching to the Traces tab, and lacks any visual hierarchy. This rewrite makes the agent's reasoning tangible and the conversation scannable.

## Scope

### In Scope
- Tailwind CSS v4 dark theme with design tokens (no component library)
- Split layout: ChatColumn (messages + composer) + AnalyticsPanel (persistent right sidebar)
- Visual tool cards for all 9 tools (see mapping below)
- Session management via localStorage with sidebar list
- Message bubbles with per-message tool trace underneath
- Empty state with clickable suggestion chips
- Health polling and status indicator

### Out of Scope
- Backend API changes (contract stays frozen)
- New tools beyond existing 9
- Phase 8 GCP deployment work
- Framer Motion animations (deferred to nice-to-have)
- Streaming response support (backend is blocking)
- Reset/clear button, team selector dropdown

## Current State Analysis

| File | State |
|------|-------|
| `App.tsx` | 237-line monolith: state, API calls, tabs, messages, memory/trace panel all inline |
| `api.ts` | Typed fetch client; expects `answer` + `tools[]` with `response` field |
| `index.css` | 387 lines of hand-written BEM-style CSS with CSS variables |
| `main.tsx` | Standard React 19 entry point |

**Problems:**
- Tool results render as raw JSON inside `<details>`/`<pre>` — unreadable for non-developers
- Traces tab fetches all session steps on every click; large traces cause UI freeze
- No visual aggregation of analytics across the conversation
- CSS is bespoke and hard to extend

**API discrepancy note:** The backend currently returns `{session_id, answer}` with no tool data bundled. The Oracle contract the user specified is `{reply, tool_trace: [{name, args, result}]}`. The frontend must either poll `/api/sessions/{id}/trace` after each turn, or a minimal backend change is needed to expose the tool trace already collected in `run_turn()`.

## Proposed Architecture

```
App.tsx ──► ChatColumn ──► MessageBubble ──► ToolTrace ──► viz/*
       │                    │
       └─► AnalyticsPanel ◄─┘ (snapshot rebuilt from all messages)
```

**Component tree (~18 files):**
- `App.tsx` — session state, message list, health polling, top header
- `components/ChatColumn.tsx` — scrollable message log + pinned composer
- `components/MessageBubble.tsx` — user/assistant bubbles with markdown
- `components/Composer.tsx` — input + send button
- `components/EmptyHero.tsx` — empty state with suggestion chips
- `components/ToolTrace.tsx` — stack of ToolCards per message turn
- `components/AnalyticsPanel.tsx` — persistent right sidebar with latest analytics
- `components/viz/SqlTable.tsx` — table renderer for `sql_query` rows
- `components/viz/ProbabilityBar.tsx` — 3-segment animated bar for `predict_match`
- `components/viz/EloGauges.tsx` — team Elo bar + match count
- `components/viz/FormTiles.tsx` — W/D/L match result tiles
- `components/viz/H2HRecord.tsx` — win/loss/draw bar + recent match list
- `components/viz/ResultList.tsx` — scored document list (vector_search / hybrid_retrieve)
- `components/viz/RawJson.tsx` — collapsible fallback for unhandled tools
- `lib/types.ts` — wire types mirroring backend contract
- `lib/api.ts` — typed fetch client with error wrapping
- `lib/analytics.ts` — `buildSnapshot()` distills messages into panel data

**Data flow:**
1. User sends message → `api.ts` POST `/api/chat`
2. Response appended to `messages` state
3. `MessageBubble` renders assistant reply + `ToolTrace` card stack
4. `AnalyticsPanel` receives `useMemo(snapshot)` rebuilt from all messages
5. Snapshot surfaces the latest prediction, Elo, form, H2H, etc.

## Tool-to-Visual Mapping

| Tool | Visual | Data Shape |
|------|--------|------------|
| `sql_query` | **SqlTable** | `{columns[], rows[][]}` — render as bordered table, cap at 8 rows |
| `vector_search` | **ResultList** | `{results: [{content, teams, score}]}` — scored cards with snippet |
| `hybrid_retrieve` | **ResultList** (with source badges) | Same shape + `sources[]` array showing "vector" / "fulltext" |
| `remember` | **StatusBadge** | `{status: "remembered"}` — green confirmation pill |
| `recall` | **FactList** | `{facts: [...]}` — numbered list of recalled facts |
| `get_team_elo` | **EloGauges** | `{elos: {team: {elo, matches}}}` — single bar + numeric readout |
| `get_team_form` | **FormTiles** | `{form: [{date, opponent, result, score, venue}]}` — W/D/L tiles |
| `get_h2h` | **H2HRecord** | `{record: {team1: N, team2: N, draws: N}, last_matches: [...]}` |
| `predict_match` | **ProbabilityBar** | `{probabilities: {team1_win, team2_win, draw}}` — 3-segment bar |

Unhandled or error results fall back to **RawJson** (collapsible, default closed).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tailwind v4 + Vite 6 plugin compatibility | Low | Pin `@tailwindcss/vite@4.x` which supports Vite 5+; test `npm run dev` immediately |
| Backend does not return `tool_trace` in chat response | Med | Poll `/api/sessions/{id}/trace` after each turn as fallback; lobby for 5-line backend fix |
| Tool result shapes differ subtly from Oracle types | Med | Adapt Oracle viz components to our shapes (e.g. `probabilities.team1_win` vs `prob_home_win`) |
| AnalyticsPanel re-renders on every keystroke | Low | `useMemo` snapshot + `memo()` on all viz components |

## Rollback Plan

1. Keep the old `App.tsx`, `api.ts`, and `index.css` on a backup branch.
2. The rewrite is additive (new files in `components/`, `lib/`); `main.tsx` import changes are minimal.
3. If broken, `git checkout` the 3 original files and delete new directories to restore the old UI in under 30 seconds.

## Estimated Effort

- **16–18 source files** (12 new components, 3 rewrites, 2–3 utility files)
- **1 focused day** of frontend implementation
- **0 backend changes** required if we accept the trace-polling fallback

## Success Criteria

- [ ] `npm run dev` starts without Tailwind/Vite errors
- [ ] Chat UI renders in dark theme with split layout on ≥lg screens
- [ ] Each of the 9 tools renders a dedicated visual card instead of raw JSON
- [ ] AnalyticsPanel persists and updates as the conversation grows
- [ ] Session ID survives page reload via localStorage
- [ ] Empty state shows suggestion chips that seed the composer
