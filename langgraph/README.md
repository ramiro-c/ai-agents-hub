# LangGraph Experiments

Experiments with [LangGraph](https://langchain-ai.github.io/langgraph/) — building agent workflows with graphs, state management, and tool integration.

## Setup

```bash
cd langgraph
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your API keys via a `.env` file in the `langgraph/` directory:

```bash
cp ../adk/.env.example .env   # or create a new one
```

The notebook uses `python-dotenv` to load environment variables automatically.

## Notebooks

### Lesson 2: Baseline Email Assistant

**File**: [`lesson2.ipynb`](lesson2.ipynb)

Builds an email assistant that classifies incoming messages and drafts responses. The notebook progresses through:

1. **Profile & context setup** — Define user profile, triage rules, and example emails
2. **Triage agent** — Classify emails as *respond*, *ignore*, or *notify* using structured output
3. **Tool definitions** — Register tools (`write_email`, `schedule_meeting`, `check_calendar_availability`) for the agent
4. **Prompt engineering** — Craft instructions that route the agent to the right tool per scenario
5. **Overall agent graph** — Compose triage → classification routing → response drafting into a single `StateGraph`
6. **End-to-end execution** — Run the graph with sample emails and inspect the output

**Concepts demonstrated**: `StateGraph`, `Command` routing, `@tool` decorators, structured output with Pydantic, and graph composition.

#### Running the Notebook

```bash
# VS Code
code lesson2.ipynb

# Jupyter
jupyter notebook lesson2.ipynb
```

## Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `langgraph` | ≥0.4 | Graph-based agent framework |
| `langchain` | ≥0.3 | LLM abstraction layer |
| `langchain-core` | ≥0.3 | Core types and utilities |
| `python-dotenv` | ≥1.0 | Environment variable loading |
| `pydantic` | ≥2.0 | Structured output schemas |

## Relationship to ADK

LangGraph and ADK serve complementary needs in this monorepo:

- **ADK** (`adk/`): Agent-first framework — define agents with system instructions, plug in tools, and run. Best for single-agent tasks and structured instruction patterns.
- **LangGraph** (`langgraph/`): Graph-first framework — define workflows as explicit state graphs with branching, routing, and multi-step orchestration. Best for complex multi-agent flows.

The [architecture doc](../docs/architecture.md) explains the rationale for maintaining both.
