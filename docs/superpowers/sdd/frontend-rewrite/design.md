# Design: Soccer Analytics Agent Frontend Rewrite

## Technical Approach

Rewrite the current 3-file monolith (App.tsx + api.ts + index.css) into ~20 modular files following the Oracle workshop's split-layout pattern (ChatColumn + AnalyticsPanel), adapted to our backend's actual data shapes. The core strategy: **adapt Oracle patterns, never copy** — our tools return different field names and nested structures than Oracle's.

## Architecture Decisions

| # | Decision | Options | Choice | Rationale |
|---|----------|---------|--------|-----------|
| 1 | Tailwind setup | Tailwind v3 CLI w/ config OR v4 `@tailwindcss/vite` | **v4 `@tailwindcss/vite`** | Matches Oracle reference; zero-config; `@theme` block in CSS replaces tailwind.config.ts |
| 2 | Backend gap: tool trace | Client-side polling OR 15-line backend patch | **Option A: polling (primary), Option B: patch (nice-to-have)** | No backend changes needed to ship; polling adds ~1.5s worst-case latency but preserves API contract freeze. Patch is documented as upgrade path. |
| 3 | Frame motion | Include or defer | **Defer** — use CSS transitions only | Framer Motion adds ~33KB gzipped; not in scope per proposal. Can add later as drop-in. |
| 4 | Markdown rendering | react-markdown OR plain text | **react-markdown (keep existing)** | Already in project deps; agent replies contain markdown tables and formatting. |
| 5 | Viz component shapes | Copy Oracle shapes OR adapt to our backend | **Adapt to our backend** | Our `predict_match` returns `{team1, probabilities: {team1_win, ...}}` not Oracle's `{home_team, prob_home_win, ...}`. Every viz component parses our actual API shapes. |
| 6 | State: session ID | React state OR localStorage | **localStorage** | Survives page reload per REQ-001; read once on mount, write on new session. |
| 7 | State: teams sidebar | Integrated into session sidebar OR only AnalyticsPanel | **Not in v1 scope** | REQ-008 (session/teams list) documented but out of scope per proposal; sidebar shows analytics only. |

## Data Flow

```
User types → Composer.onSend(text)
  → api.sendChat(text, sessionId) → POST /api/chat {session_id, message}
    ← {session_id, answer}
  → append Message to messages state
  → REQ-004: poll /api/sessions/{id}/trace
    ← {trace: [{turn_id, step, content}]}
  → filter by current turn_id, extract calls from kind="tool_calls" steps
  → merge tool_trace into Message, setMessages
  → MessageBubble renders text + ToolTrace stack
  → AnalyticsPanel: useMemo(buildSnapshot) distills latest prediction/elo/form/h2h into sidebar
  → HealthPill: useEffect interval polls /api/health every 20s
```

**Turn identification for polling**: count `messages.filter(m => m.role === "assistant").length` as `turn_id`. The backend trace stores turn_id incrementally per session, matching this 1-based counter.

## Component Architecture

### Component Tree with Props

```
<App>                                    — sessionId, healthStatus, teams[]
  <HealthPill status: HealthStatus />     — green/amber/red dot
  <main>
    <ChatColumn messages: Message[] busy: boolean onSend: (text)=>void >
      <EmptyHero onPick: (q)=>void />    — when messages.length === 0
      <MessageBubble message: Message />  — role: "user" | "assistant"
        <ToolTrace trace: ToolCall[] />   — only for assistant messages
          <ToolCard call: ToolCall />     — dispatches to viz by call.name
            ├── <SqlTable data: SqlResult />
            ├── <ResultList data: SearchResult variant: "vector"|"hybrid" />
            ├── <StatusBadge data: RememberResult />
            ├── <FactList data: RecallResult />
            ├── <EloGauges data: EloResult />
            ├── <FormTiles data: FormResult />
            ├── <H2HRecord data: H2HResult />
            ├── <ProbabilityBar data: PredictResult variant: "inline" />
            └── <RawJson data: unknown />
      <Composer onSend: (text)=>void busy: boolean />
    </ChatColumn>
    <AnalyticsPanel snapshot: AnalyticsSnapshot />  — persistent right sidebar
      ├── <ProbabilityBar data: PredictResult variant: "hero" />
      ├── <EloGauges data: EloResult />
      ├── <FormTiles data: FormResult />
      └── <H2HRecord data: H2HResult />
```

### Core Type Shapes (from our backend)

```typescript
// From POST /api/chat response (current contract)
interface ChatResponse { session_id: string; answer: string; }

// From GET /api/sessions/{id}/trace response
interface TraceResponse { session_id: string; trace: TraceStep[]; }
interface TraceStep { turn_id: number; step: number; content: TraceContent; }

// Trace content shapes (from loop.py save_step calls)
type TraceContent =
  | { kind: "answer"; text: string }
  | { kind: "tool_calls"; calls: RawToolCall[] };

interface RawToolCall { tool: string; args: Record<string, unknown>; result: Record<string, unknown>; }

// Our app types (after parsing trace)
interface ToolCall { name: string; args: Record<string, unknown>; result: Record<string, unknown>; }
interface Message { id: string; role: "user" | "assistant"; text: string; trace?: ToolCall[]; isError?: boolean; }

// Viz-specific types (matching our tool return shapes)
interface SqlResult { columns: string[]; rows: (string|null)[][]; }
interface SearchResult { results: Array<{ content: string; teams: string; score: number; sources?: string[] }>; }
interface EloResult { elos: Record<string, { elo: number; matches: number }>; not_found?: string[] | null; }
interface FormResult { team: string; form: Array<{ date: string; opponent: string; result: "W"|"D"|"L"; score: string; venue: string }>; last_n: number; }
interface H2HResult { team1: string; team2: string; record: Record<string, number>; total: number; last_matches: Array<{ date: string; score: string }>; }
interface PredictResult { team1: string; team2: string; probabilities: { team1_win: number; team2_win: number; draw: number }; prediction_note: string; }
interface AnalyticsSnapshot { prediction?: PredictResult; elo: EloResult[]; form: FormResult[]; h2h?: H2HResult; subjectTeams: string[]; }
```

## Tool-to-Component Mapping

| Tool | Component | Props | Backend Result Shape Used |
|------|-----------|-------|--------------------------|
| `sql_query` | `SqlTable` | `{data: SqlResult}` | `columns[]`, `rows[][]` from tool result |
| `vector_search` | `ResultList` | `{data: SearchResult, variant: "vector"}` | `results[{content, teams, score}]` |
| `hybrid_retrieve` | `ResultList` | `{data: SearchResult, variant: "hybrid"}` | `results[{content, teams, sources[]}]` |
| `remember` | `StatusBadge` | `{status: string}` | `result.status` field |
| `recall` | `FactList` | `{facts: string[]}` | `result.facts[]` field |
| `get_team_elo` | `EloGauges` | `{data: EloResult}` | `elos` record, entry per team |
| `get_team_form` | `FormTiles` | `{data: FormResult}` | `form[]` array of match dicts |
| `get_h2h` | `H2HRecord` | `{data: H2HResult}` | `record` + `last_matches[]` |
| `predict_match` | `ProbabilityBar` | `{data: PredictResult}` | `probabilities.{team1_win, team2_win, draw}` |

Error case: if `result.error` exists → render error card with tool name + error message.

## State Management

| State | Location | Init | Updates |
|-------|----------|------|---------|
| `sessionId` | `localStorage` + `useState` | UUID v4 if absent | On new session button OR 404 recovery |
| `messages: Message[]` | `useState` in App | `[]` | User send → append user; API response → append assistant; poll result → merge trace |
| `busy: boolean` | `useState` in App | `false` | True during send+trace poll; false after |
| `healthStatus` | `useState` in App | `"connecting"` | Polled every 20s via `getHealth()` |
| `snapshot` | `useMemo` in App | Derived | Rebuilds from all messages on every message change |
| `teams` | `useState` in App | `[]` | Fetched from `GET /api/teams` on mount |

## Tailwind v4 Setup

**Steps against existing Vite 6 + React 19 project:**

1. Add deps: `npm i -D @tailwindcss/vite tailwindcss`
2. Modify `vite.config.ts` — add `import tailwindcss from "@tailwindcss/vite"` and include in plugins array
3. Replace `src/index.css` content with `@import "tailwindcss"` + `@theme` block (Oracle's dark theme tokens)
4. Delete all BEM-style CSS — Tailwind utility classes replace everything
5. Verify with `npm run dev`

No `tailwind.config.ts` needed — v4 uses CSS-first config.

## Backend Gap: Trace Data

### Option A: Client-Side Polling (primary, zero backend changes)

```
POST /api/chat → {session_id, answer}
→ display answer immediately
→ poll GET /api/sessions/{id}/trace (3 retries, 500ms intervals)
→ parse: trace[i].content.kind === "tool_calls" → extract calls[]
→ merge into message.trace, re-render
```

**Tradeoff**: ~1.5s worst-case latency before tool cards appear. Answer text visible instantly.

### Option B: Backend Patch (recommended upgrade)

In `backend/main.py`, modify `ChatResponse` and `chat()`:

```python
class ToolCall(BaseModel):
    name: str
    args: dict
    result: dict

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    tool_trace: list[ToolCall] = []

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or f"web-{uuid.uuid4().hex[:8]}"
    answer = await asyncio.to_thread(
        respond, _client, session_id, req.message, model="gemini-2.5-flash"
    )
    last_turn = trace.get_last_turn_id(session_id)
    steps = trace.get_turn_trace(session_id, last_turn)
    tool_trace = []
    for s in steps:
        if s["content"].get("kind") == "tool_calls":
            for c in s["content"].get("calls", []):
                tool_trace.append(ToolCall(name=c["tool"], args=c["args"], result=c["result"]))
    return ChatResponse(session_id=session_id, answer=answer, tool_trace=tool_trace)
```

**Tradeoff**: Requires modifying backend (out of scope), but eliminates polling latency and complexity entirely. Frontend detects `tool_trace` in response → skips polling.

## File Structure

| File | Action | Description |
|------|--------|-------------|
| `vite.config.ts` | Modify | Add `@tailwindcss/vite` plugin |
| `package.json` | Modify | Add tailwind deps; keep react-markdown + remark-gfm |
| `src/index.css` | Replace | Tailwind v4 `@import` + `@theme` dark tokens |
| `src/main.tsx` | Keep | Unchanged entry point |
| `src/App.tsx` | Rewrite | Split layout, state management, health polling |
| `src/api.ts` | Rewrite | Typed fetch to our actual endpoints (not Oracle contract) |
| `src/lib/types.ts` | Create | All TypeScript interfaces (Message, ToolCall, viz types, TraceContent) |
| `src/lib/analytics.ts` | Create | `buildSnapshot(messages)` — distills messages into AnalyticsSnapshot |
| `src/lib/format.ts` | Create | `pct()`, `signed()`, `num2()` display helpers |
| `src/components/HealthPill.tsx` | Create | Status dot + label from health polling |
| `src/components/ChatColumn.tsx` | Create | Scrollable message log + pinned Composer |
| `src/components/MessageBubble.tsx` | Create | User/assistant bubble with markdown |
| `src/components/Composer.tsx` | Create | Textarea + send button |
| `src/components/EmptyHero.tsx` | Create | Suggestion chips for empty state |
| `src/components/ToolTrace.tsx` | Create | Stack of ToolCards per message, dispatches tool name → viz |
| `src/components/AnalyticsPanel.tsx` | Create | Right sidebar showing latest prediction/elo/form/h2h |
| `src/components/viz/SqlTable.tsx` | Create | HTML table from `SqlResult` |
| `src/components/viz/ResultList.tsx` | Create | Scored search result cards |
| `src/components/viz/StatusBadge.tsx` | Create | Green "Remembered" pill |
| `src/components/viz/FactList.tsx` | Create | Numbered list of recalled facts |
| `src/components/viz/EloGauges.tsx` | Create | Team Elo bars with match count |
| `src/components/viz/FormTiles.tsx` | Create | W/D/L match result tiles |
| `src/components/viz/H2HRecord.tsx` | Create | Win/loss/draw summary bar + match list |
| `src/components/viz/ProbabilityBar.tsx` | Create | 3-segment probability bar |
| `src/components/viz/RawJson.tsx` | Create | Collapsible JSON fallback (default closed) |

## Migration Plan

1. **Branch**: `feat/frontend-rewrite` from main
2. **Setup first** (non-breaking): `npm i -D @tailwindcss/vite tailwindcss`, modify `vite.config.ts`, replace `index.css`. Verify `npm run dev` starts.
3. **Create new files**: All `src/lib/*` and `src/components/**/*` — no old files touched yet.
4. **Rewrite App.tsx locally**: Refactor to split layout. Rename old `api.ts` to `api.old.ts` (or delete — git history preserves it).
5. **Remove old files**: Delete `api.ts` (replaced by new `src/api.ts`), `index.css` BEM classes (gone), old monolithic `App.tsx` logic.
6. **Rollback**: `git checkout main -- soccer-analytics-agent/frontend/src/App.tsx soccer-analytics-agent/frontend/src/api.ts soccer-analytics-agent/frontend/src/index.css && rm -rf soccer-analytics-agent/frontend/src/components/ soccer-analytics-agent/frontend/src/lib/`

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Manual | `npm run dev` starts, sends message, sees tool cards | Visual check against dev backend |
| Manual | Empty state shows suggestion chips, click triggers send | Visual |
| Manual | AnalyticsPanel updates after prediction message | Visual |
| Manual | Trace polling fallback: answer visible before tool cards appear | Visual + timing |
| Manual | Error handling: stop backend, verify error banner not crash | Visual |

No unit tests in scope — frontend testing infra not set up.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Open Questions

None. All types verified against actual `loop.py` trace output and `tools.py` return shapes.
