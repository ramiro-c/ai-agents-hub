# ADK Agents

Google [Agent Development Kit](https://google.github.io/adk-docs/) agents exploring different patterns — from basic `LlmAgent` configuration to structured output, planning, tool integration, and programmatic execution.

## Setup

```bash
cd adk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For Gemini-based agents, set your API key:

```bash
cp .env.example .env   # add GOOGLE_API_KEY
```

For OpenRouter-based agents, set `OPENROUTER_API_KEY` and optionally `OPENROUTER_BASE_URL` in `.env` or via the ADK API server.

## Agents by Pattern

### Basic Agent

| Agent | Pattern | Description |
|-------|---------|-------------|
| [`my_first_agent`](my_first_agent/agent.py) | `LlmAgent` with Gemini | Algebra tutor using the simplest ADK constructor: model, name, description, instruction. No planner, no tools. |
| [`my_config_agent`](my_config_agent/root_agent.yaml) | YAML-configured agent | Same math tutor, defined declaratively in `root_agent.yaml`. Zero Python — ADK loads the YAML and builds the agent. |

### Structured Output

| Agent | Pattern | Description |
|-------|---------|-------------|
| [`product_extractor`](product_extractor/agent.py) | `output_schema` + Pydantic | Extracts product info from user messages into typed JSON (`ProductInfo`). Demonstrates `output_schema` with `BaseModel`, field constraints, and `output_key` for session state. |

### Planning

| Agent | Pattern | Description |
|-------|---------|-------------|
| [`problem_solver`](problem_solver/agent.py) | `PlanReActPlanner` + LiteLLM | Strategic problem solver using ADK's `PlanReActPlanner` for multi-step reasoning. Uses **OpenRouter** via LiteLLM to access non-Gemini models. |

### Tools

| Agent | Pattern | Description |
|-------|---------|-------------|
| [`research_assistant`](research_assistant/agent.py) | Built-in `google_search` | Answers questions using live Google Search. Demonstrates ADK's built-in tool integration. Requires Gemini 2.0+. |
| [`math_assistant`](math_assistant/agent.py) | `BuiltInCodeExecutor` | Executes Python code for calculations and math problems. Demonstrates ADK's code execution tool for precision. Requires Gemini 2.0+. |
| [`geography_assistant`](geography_assistant/agent.py) | `McpToolset` (filesystem) | Reads and lists files via MCP filesystem server. Demonstrates MCP tool integration with read-only tool filters for safety. |

### Programmatic Runner

| Agent | Pattern | Description |
|-------|---------|-------------|
| [`programmatic_agent.py`](programmatic_agent.py) | `Runner` + `InMemorySessionService` | Math tutor executed entirely in Python (no CLI). Demonstrates sessions, async runner, and manual message handling. |

### Full-stack Integration

| Agent | Pattern | Description |
|-------|---------|-------------|
| [`customer-support-chat/agent`](../customer-support-chat/agent/agent.py) | Structured instructions + OpenRouter | Full production agent (Alex Chen, Spanish persona). Demonstrates identity/mission/methodology/limits pattern in instruction writing. See [customer-support-chat/README.md](../customer-support-chat/README.md). |

## Running Agents

```bash
# Interactive mode
adk run problem_solver

# Non-interactive (replay)
echo '{"state": {}, "queries": ["What is 2+2?"]}' | adk run --replay /dev/stdin problem_solver

# Web UI
adk web problem_solver
```

## Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `google-adk` | 2.2.0 | Agent framework |
| `litellm` | 1.83.x | OpenRouter model access |
| `ruff` | — | Lint + format via pre-commit |

## Pre-commit

Ruff hooks run automatically on `git commit`. Manual run:

```bash
adk/.venv/bin/pre-commit run --all-files
```

## Adding a New Agent

1. Create a directory: `adk/my_new_agent/`
2. Add `agent.py` (or `root_agent.yaml`) following existing patterns
3. Set up a `__init__.py` if needed
4. Update this README — add your agent under the matching pattern category

See [CONTRIBUTING.md](../CONTRIBUTING.md) for conventions.
