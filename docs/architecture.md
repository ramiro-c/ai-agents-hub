# Architecture

AI Agents Hub is a monorepo of agent experiments and applications. This document explains the structural and technology decisions.

## Monorepo Rationale

### Decision

All agent experiments live in a single repository rather than separate repos per framework or per agent.

### Reasoning

- **Shared tooling**: Ruff config (`pyproject.toml`), pre-commit hooks, and `.gitignore` apply across all subprojects.
- **Low overhead per experiment**: Each agent is ~20–80 lines. A separate repo per agent would create disproportionate maintenance cost.
- **Cross-reference value**: ADK and LangGraph experiments document complementary approaches. A contributor exploring agents can compare patterns in one place.
- **Single source of truth for conventions**: Branch naming, PR size guidelines, and code style live in one `CONTRIBUTING.md`.

### Tradeoffs

| Pro | Con |
|-----|-----|
| Unified linting, pre-commit, and config | Subproject-specific tooling (e.g., Node for frontend) adds environment complexity |
| Easy cross-referencing between frameworks | Root README must stay current with all subprojects |
| Single `CONTRIBUTING.md` for all contributors | Different subprojects have different setup steps |

## ADK vs LangGraph Split

### Decision

Use **Google ADK** for single-agent experiments and **LangGraph** for graph-based multi-step workflows. Maintain both in the same monorepo.

### ADK (`adk/`)

Agent-first framework. Define an agent with a system instruction, attach tools, and run.

**Strengths for this project**:
- Low boilerplate — agents are 15–70 lines
- Built-in tools: `google_search`, `BuiltInCodeExecutor`, MCP integration
- Built-in planners: `PlanReActPlanner`
- CLI and web UI out of the box (`adk run`, `adk web`)
- YAML-configurable agents (no Python needed for basic cases)

**Current ADK agents**: 8 experimental agents + 1 full-stack integration (customer-support-chat).

### LangGraph (`langgraph/`)

Graph-first framework. Define nodes, edges, and conditional routing as an explicit `StateGraph`.

**Strengths for this project**:
- Explicit control flow — branching, loops, parallel execution visible in the graph
- Structured state management with Pydantic schemas
- Natural fit for multi-step workflows (triage → classify → respond → schedule)
- Strong ecosystem (LangChain, LangSmith for tracing)

**Current LangGraph content**: `lesson2.ipynb` — email triage and response drafting as a `StateGraph`.

### When to Use Which

| Scenario | Framework |
|----------|-----------|
| Single-agent task with tool use | ADK |
| Agent with built-in Gemini tools (search, code exec) | ADK |
| Multi-step workflow with branching logic | LangGraph |
| Explicit state machine or graph-based routing | LangGraph |
| Quick prototype or experiment | ADK |
| Production agent with structured instructions | ADK |

## LiteLLM + OpenRouter

### Decision

Use **LiteLLM** as the model adapter and **OpenRouter** as the model gateway for agents that need non-Gemini models.

### Reasoning

- **Model flexibility**: OpenRouter provides access to 200+ models through a single API. LiteLLM normalizes the interface so ADK sees a consistent model shape.
- **No vendor lock-in**: Agents using `resolve_model(provider="openrouter")` can switch to any OpenRouter model by changing the model string in `model_utils.py`.
- **Centralized config**: All model selection goes through `adk/model_utils.py` (Strategy pattern). Set `MODEL_PROVIDER` in `adk/.env` and individual agents don't hardcode model strings.

### Scope

All agents now use the centralized `resolve_model()` factory. Gemini agents pass `resolve_model(provider="gemini")` explicitly because they depend on Gemini-specific tooling (Google Search, code execution). OpenRouter agents use `resolve_model(provider="openrouter")`.

| Agent | Model Adapter |
|-------|---------------|
| `my_first_agent` | Gemini native (`resolve_model(provider="gemini")`) |
| `my_config_agent` | Gemini native (YAML — `model: gemini-2.5-flash`) |
| `product_extractor` | OpenRouter (`resolve_model(provider="openrouter")`) |
| `problem_solver` | OpenRouter (`resolve_model()`) |
| `research_assistant` | Gemini native (`resolve_model(provider="gemini")`) |
| `math_assistant` | Gemini native (`resolve_model(provider="gemini")`) |
| `file_reader_assistant` | OpenRouter (`resolve_model(provider="openrouter")`) |
| `programmatic_agent.py` | Gemini native |
| `customer-support-chat/agent` | OpenRouter |

## Frontend Architecture

### Decision

Single frontend app (React) in `customer-support-chat/frontend/`. No shared frontend framework across subprojects.

### Reasoning

- Only one subproject (`customer-support-chat`) needs a UI. ADK and LangGraph experiments are CLI/notebook-driven.
- A shared component library would be premature without more UI consumers.
- Vite + React provides fast dev iteration for the chat UI.

## Directory Conventions

```
ai-agents-hub/
├── adk/                        # ADK agents — one directory per agent
│   ├── <agent_name>/           #   agent.py + optional __init__.py
│   └── programmatic_agent.py   #   standalone script (no directory)
├── langgraph/                  # LangGraph notebooks + requirements
├── customer-support-chat/      # Full-stack app
│   ├── agent/                  #   ADK agent
│   ├── backend/                #   FastAPI proxy
│   └── frontend/               #   React UI
├── docs/                       # Architecture and meta documentation
├── .pre-commit-config.yaml     # Ruff hooks
├── pyproject.toml              # Ruff configuration
└── CONTRIBUTING.md             # Contributor guide
```

### Convention: Python Virtual Environments

Each subproject manages its own `.venv`:

| Subproject | `.venv` location |
|------------|-----------------|
| `adk/` | `adk/.venv/` |
| `langgraph/` | `langgraph/.venv/` |
| `customer-support-chat/agent/` | `customer-support-chat/agent/.venv/` |
| `customer-support-chat/backend/` | `customer-support-chat/backend/.venv/` |

Pre-commit hooks run from `adk/.venv/` (the only venv that installs `pre-commit`).

## Testing Strategy

### Current State

No automated test suite. Testing is manual:
- `adk run <agent>` for interactive verification
- `adk web <agent>` for visual inspection
- Ruff lint + format via pre-commit for code quality

### Future Direction

- Unit tests for agent instruction effectiveness (ADK eval framework)
- Integration tests for `customer-support-chat` backend
- Notebook execution tests for LangGraph

Test infrastructure contributions are welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Design Decisions (ADR Index)

| ADR | Decision | Status |
|-----|----------|--------|
| 1 | Monorepo for all agent experiments | Active |
| 2 | ADK for single-agent, LangGraph for graph-based | Active |
| 3 | LiteLLM + OpenRouter for non-Gemini models | Active |
| 4 | Separate `.venv` per subproject | Active |
| 5 | Ruff for lint/format (no Black, no isort) | Active |
