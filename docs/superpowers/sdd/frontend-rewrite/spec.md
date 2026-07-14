# Soccer Analytics Agent Frontend — Functional Specification

## Purpose

Define the behavioral contract for the Soccer Analytics Agent frontend rewrite. This spec describes WHAT the UI does, not HOW it looks. Every requirement is testable; every scenario uses Given/When/Then.

---

## Functional Requirements

### REQ-001: Session Persistence

The application MUST persist a session ID in `localStorage` and reuse it across page reloads. If no session ID exists, the application MUST generate a UUID v4 and store it before sending the first message.

#### Scenario: First visit

- GIVEN a first-time visitor opens the app
- WHEN the page loads
- THEN a new UUID v4 session ID is generated and stored in `localStorage`
- AND the UI shows an empty conversation state with suggestion chips

#### Scenario: Returning visitor

- GIVEN a user who has previously visited the app
- WHEN the page loads
- THEN the stored session ID is read from `localStorage`
- AND the previous conversation history is NOT automatically loaded (new conversation in same session)

#### Scenario: Storage unavailable

- GIVEN `localStorage` is disabled or full
- WHEN the page loads
- THEN the application generates a session ID in memory only
- AND a non-blocking warning is displayed to the user

---

### REQ-002: Send Message

The application MUST send user messages via `POST /api/chat` with `{session_id, message}` and display the response `{session_id, answer}`.

#### Scenario: Successful message send

- GIVEN the user has typed a non-empty message
- WHEN the user submits the message
- THEN the message appears immediately in the conversation as a user bubble
- AND a loading indicator is shown for the assistant response
- AND when the response arrives, the assistant answer is displayed below the user message
- AND the input is cleared and re-enabled

#### Scenario: Empty message rejection

- GIVEN the input field is empty or contains only whitespace
- WHEN the user attempts to submit
- THEN the message is NOT sent
- AND the submit control remains disabled or the submission is silently ignored

#### Scenario: Concurrent send prevention

- GIVEN a message is currently being processed (loading state active)
- WHEN the user attempts to send another message
- THEN the send control is disabled until the current response is received

---

### REQ-003: Tool Trace Display

The application MUST display structured visual cards for each recognized tool result attached to an assistant message. Unrecognized tool results MUST fall back to a collapsible raw JSON display.

#### Scenario: Recognized tool result

- GIVEN an assistant message contains a tool trace for a known tool (one of the 9 defined tools)
- WHEN the message is rendered
- THEN a dedicated visual card appropriate to that tool type is displayed
- AND the card renders the tool's result data according to its data shape (see Data Shape Tables)

#### Scenario: Unrecognized tool result

- GIVEN an assistant message contains a tool trace for an unknown tool
- WHEN the message is rendered
- THEN a collapsible raw JSON block is displayed, collapsed by default
- AND expanding it shows the full tool name and result payload

#### Scenario: No tools called in a turn

- GIVEN the assistant responded without invoking any tools
- WHEN the message is rendered
- THEN only the text answer is displayed
- AND no tool trace section or empty placeholder is shown

---

### REQ-004: Tool Trace Polling Fallback

Because the backend `POST /api/chat` currently returns only `{session_id, answer}` without tool trace data, the application MUST poll `GET /api/sessions/{id}/trace` after each successful chat response to retrieve tool execution steps.

#### Scenario: Polling after chat response

- GIVEN a successful `POST /api/chat` response has been received
- WHEN the assistant answer is displayed
- THEN the application sends `GET /api/sessions/{session_id}/trace`
- AND matches returned trace steps to the current turn by `turn_id`
- AND renders tool cards for each step where `kind` indicates a tool result

#### Scenario: Polling retry on empty trace

- GIVEN the first trace poll returns no new steps for the current turn
- WHEN the trace response is empty or contains only prior-turn steps
- THEN the application retries up to 3 times with 500ms intervals
- AND if still empty after retries, displays the answer without tool cards

#### Scenario: Polling failure

- GIVEN the trace endpoint returns an error (4xx/5xx)
- WHEN the poll request fails
- THEN the assistant answer is still displayed normally
- AND a subtle indicator notes that tool details are unavailable

---

### REQ-005: Analytics Panel

The application MUST maintain a persistent analytics sidebar that aggregates the latest analytics data from all tool results across the conversation.

#### Scenario: Panel updates on new analytics data

- GIVEN the conversation contains tool results from `predict_match`, `get_team_elo`, `get_team_form`, or `get_h2h`
- WHEN a new message with analytics tool results is received
- THEN the analytics panel updates to show the latest values
- AND previous analytics data is replaced (not appended) for the same tool type

#### Scenario: Empty analytics state

- GIVEN no analytics-relevant tools have been called in the conversation
- WHEN the analytics panel is visible
- THEN the panel shows an empty state indicating no analytics data is available yet

---

### REQ-006: Suggestion Chips

The application MUST display clickable suggestion chips when the conversation is empty. Selecting a chip MUST populate and submit the message input.

#### Scenario: Chip click sends message

- GIVEN the conversation is empty and suggestion chips are visible
- WHEN the user clicks a suggestion chip
- THEN the chip's text is sent as a user message
- AND the chips disappear (conversation is no longer empty)

---

### REQ-007: Health Status Indicator

The application MUST poll `GET /api/health` at regular intervals and display a visual status indicator.

#### Scenario: Healthy backend

- GIVEN the health endpoint returns `{status: "ok"}` (or similar healthy response)
- WHEN the health poll completes
- THEN a positive status indicator is displayed (e.g., green dot)

#### Scenario: Unhealthy or unreachable backend

- GIVEN the health endpoint returns an error or does not respond within 5 seconds
- WHEN the health poll completes or times out
- THEN a negative status indicator is displayed (e.g., red dot)
- AND the message input remains usable (user can still attempt to send)

---

### REQ-008: Session List

The application MUST display a list of available teams via `GET /api/teams` and allow viewing team details via `GET /api/teams/{name}`.

#### Scenario: Teams list loads

- GIVEN the application starts
- WHEN the teams endpoint responds successfully
- THEN a list of team names is displayed

#### Scenario: Team detail view

- GIVEN the teams list is displayed
- WHEN the user selects a team
- THEN the application fetches `GET /api/teams/{name}`
- AND displays the team's Elo rating and match count

---

### REQ-009: Error Handling

The application MUST handle all API errors gracefully without crashing or showing raw error objects.

#### Scenario: Chat API failure

- GIVEN the user sends a message
- WHEN `POST /api/chat` returns a non-2xx response or network error
- THEN an error message is displayed in the conversation (not a browser alert)
- AND the user's message remains visible
- AND the input is re-enabled for retry

#### Scenario: Backend unreachable

- GIVEN the backend server is down
- WHEN the user sends a message
- THEN a connection error is displayed
- AND the health indicator shows unhealthy status

---

## Data Shape Tables

### sql_query

| Field | Type | Display |
|-------|------|---------|
| `columns` | `string[]` | Table headers |
| `rows` | `any[][]` | Table body rows |
| `row_count` | `number` | Footer: "N rows returned" |

Display: Bordered table. Cap visible rows at 8 with scroll or "show more" expansion.

---

### vector_search

| Field | Type | Display |
|-------|------|---------|
| `results[].content` | `string` | Text snippet (truncated to ~200 chars) |
| `results[].teams` | `string[]` | Team name badges |
| `results[].score` | `number` | Relevance score indicator |

Display: Stacked cards, each showing snippet, team badges, and score.

---

### hybrid_retrieve

| Field | Type | Display |
|-------|------|---------|
| `results[].content` | `string` | Text snippet |
| `results[].teams` | `string[]` | Team name badges |
| `results[].vector_score` | `number` | Vector similarity score |
| `results[].text_score` | `number` | Full-text search score |
| `results[].rrf_score` | `number` | Reciprocal rank fusion score (primary display) |
| `sources` | `string[]` | Source badges: "vector", "fulltext" |

Display: Same as vector_search cards, plus source badges and RRF score as primary ranking indicator.

---

### remember

| Field | Type | Display |
|-------|------|---------|
| `status` | `"remembered"` | Green confirmation pill: "Remembered" |

Display: Single status badge. No additional data.

---

### recall

| Field | Type | Display |
|-------|------|---------|
| `facts` | `string[]` | Numbered list of fact strings |

Display: Ordered list, each fact as a readable line item.

---

### get_team_elo

| Field | Type | Display |
|-------|------|---------|
| `elos` | `Record<string, {elo: number, matches: number}>` | Per-team: Elo value + match count |

Display: For each team key — team name label, Elo numeric value, and matches played count.

---

### get_team_form

| Field | Type | Display |
|-------|------|---------|
| `form[].date` | `string` | Match date |
| `form[].opponent` | `string` | Opponent team name |
| `form[].result` | `"W" \| "D" \| "L"` | Color-coded result tile |
| `form[].score` | `string` | Score string (e.g., "2-1") |
| `form[].venue` | `string` | Venue label (home/away) |

Display: Horizontal row of result tiles, color-coded by W/D/L, showing score and opponent.

---

### get_h2h

| Field | Type | Display |
|-------|------|---------|
| `record.team1` | `number` | Team 1 win count |
| `record.team2` | `number` | Team 2 win count |
| `record.draws` | `number` | Draw count |
| `last_matches[].date` | `string` | Match date |
| `last_matches[].score` | `string` | Score string |
| `last_matches[].venue` | `string` | Venue |

Display: Summary bar showing W/D/L counts + list of recent match results.

---

### predict_match

| Field | Type | Display |
|-------|------|---------|
| `probabilities.team1_win` | `number` (0–1) | Team 1 win probability segment |
| `probabilities.team2_win` | `number` (0–1) | Team 2 win probability segment |
| `probabilities.draw` | `number` (0–1) | Draw probability segment |
| `analysis` | `string` | Textual analysis paragraph |

Display: 3-segment horizontal bar with percentages + analysis text below.

---

## Edge Cases

### Backend is down

- All API calls fail → inline error messages, no crashes
- Health indicator turns red
- User can still type and attempt to send (errors shown per-message)

### Session expires or becomes invalid

- If `POST /api/chat` returns 404 for a stored session ID → clear the session ID from `localStorage`, generate a new one, and notify the user that the session was reset

### Tool result is empty

- `sql_query` with `row_count: 0` → show table headers with "No results" message
- `vector_search` / `hybrid_retrieve` with empty `results[]` → show "No matches found" message
- `recall` with empty `facts[]` → show "No facts recalled" message
- `get_team_form` with empty `form[]` → show "No recent matches" message

### Tool returns an error

- If a tool step in the trace has an error status → display an error card with the tool name and error message instead of the normal visual card

### User sends empty message

- Whitespace-only input is rejected; submit control is disabled or submission is silently ignored

### No tools called in a turn

- Assistant message displays text answer only, no tool trace section rendered

### Very large tool results

- `sql_query` with >8 rows → cap display at 8 rows with expansion control
- Long text snippets in `vector_search`/`hybrid_retrieve` → truncate at ~200 characters with ellipsis
- `recall` with many facts → show first 10 with "show more" expansion

### Trace polling returns stale data

- Filter trace steps by `turn_id` matching the current turn; ignore steps from prior turns

---

## Tool Trace Polling Fallback — Detailed Flow

The backend `POST /api/chat` returns `{session_id, answer}` only. Tool trace data is available separately via `GET /api/sessions/{id}/trace`. The frontend MUST bridge this gap:

```
1. User sends message
2. POST /api/chat {session_id, message}
3. Response: {session_id, answer}
4. Display assistant answer immediately
5. GET /api/sessions/{session_id}/trace
6. Response: [{turn_id, step, kind, content}]
7. Filter steps where turn_id matches the current conversation turn
8. For each step where kind indicates a tool result:
   a. Parse content to identify tool name and result data
   b. Render the appropriate tool card below the assistant message
9. If no new steps found:
   a. Retry up to 3 times at 500ms intervals
   b. After 3 retries with no new data, render answer without tool cards
10. If trace endpoint errors:
    a. Display answer without tool cards
    b. Show subtle "tool details unavailable" indicator
```

**Turn identification**: The current turn is identified by counting assistant messages in the conversation. The trace endpoint's `turn_id` field is matched against this count. If the backend uses a different turn identification scheme, the polling logic MUST adapt to match.

**Future upgrade path**: If the backend is updated to return `{reply, tool_trace: [{name, args, result}]}` directly in the chat response, the polling mechanism SHOULD be bypassed entirely — detect the presence of `tool_trace` in the response and skip polling when available.
