# ADK Conventions

Coding conventions that apply to every agent in this project. For setup and running instructions, see [README.md](README.md).

## 1. Model Resolution

Every agent must resolve its model through `model_utils.resolve_model()`. Never hardcode a model string.

```python
from model_utils import resolve_model
```

Choose the provider explicitly based on what the agent needs:

| Argument | When to use |
|----------|-------------|
| `resolve_model(provider="gemini")` | Agent requires Gemini (Google Search, code execution, ADK built-in tools) |
| `resolve_model(provider="openrouter")` | Agent is LLM-agnostic, needs OpenRouter access |
| `resolve_model()` | Agent defers to `MODEL_PROVIDER` env var — use sparingly, makes behavior opaque |

**Rationale**: Centralized model resolution means switching providers only requires changing an env var. Explicit `provider=` makes the agent's requirement visible in source code.

## 2. Agent Variable Naming

The `LlmAgent` instance must be named `root_agent`. The internal `name=` parameter must match the directory name.

```python
# Directory: adk/travel_agent/
root_agent = LlmAgent(
    model=resolve_model(provider="openrouter"),
    name="travel_agent",          # matches directory name
    ...
)
```

**Rationale**: Every `__init__.py` imports `root_agent` from `.agent`. That contract breaks if the variable name differs. Matching `name=` to the directory avoids collisions when multiple agents are loaded in the same ADK runtime.

## 3. `__init__.py` Pattern

Every agent directory's `__init__.py` follows this exact 3-line skeleton:

```python
from .agent import root_agent

__all__ = ["root_agent"]
```

No other content. No comments. No extra imports.

**Rationale**: ADK discovers agents by scanning package `__init__.py` files. The `root_agent` export is the contract. `__all__` makes the public API explicit.

## 4. Import Order

Three blocks, separated by a single blank line:

```python
# Block 1: Standard library (if needed)
import os
from pathlib import Path

# Block 2: Third-party / framework
from google.adk.agents import LlmAgent
from google.adk.planners import PlanReActPlanner

# Block 3: Local (project-level)
from model_utils import resolve_model
```

- Block 1 is optional — omit if the agent needs no stdlib imports.
- Block 2 always imports `LlmAgent` from `google.adk.agents`.
- Block 3 always imports `resolve_model` from `model_utils`.
- No blank lines inside a block.

## 5. Instruction String Format

Triple-double-quote, text starts immediately after the opening `"""`:

```python
instruction="""You are a helpful travel agent assistant.

Your capabilities:
- Search for flights
- Search for hotels
- Calculate trip budgets

Be friendly and help users plan their perfect trip!""",
```

Rules:
- No leading whitespace or `\n` after the opening `"""`
- No trailing whitespace or `\n` before the closing `"""`
- Single blank line between logical sections inside the string
- Use bullet lists (`-`) for capabilities, numbered lists (`1.`) for steps

## 6. Tool Function Conventions

### Docstrings

Google-style with three sections:

```python
def search_flights(destination: str, departure_date: str) -> dict:
    """One-line summary of what the tool does.

    Use this tool when a customer wants to know flight options.

    Args:
        destination (str): The destination city (e.g., "Paris", "Tokyo").
        departure_date (str): Departure date in YYYY-MM-DD format.

    Returns:
        dict: Flight search results.
            On success: {'status': 'success', 'flights': [...], 'count': N}
            On error: {'status': 'error', 'error_message': 'explanation'}
    """
```

- **Summary line**: What the tool does.
- **Guidance line**: "Use this tool when..." — tells the LLM when to invoke it.
- **Args**: Parameter name, type in parens, description. Include example values.
- **Returns**: Describe the dict shape — both success and error forms.

### Tool headers

Comment block above each tool function:

```python
# Tool 1: Search flights
def search_flights(...):
```

### Error handling

Never raise exceptions. Return an error dict:

```python
return {
    "status": "error",
    "error_message": "No flights found to Paris. Try New York or Tokyo.",
}
```

Success uses the same shape with `"status": "success"` and domain-specific data.

### Return type

Always `-> dict`. ADK introspects the function signature and docstring — no decorators or `FunctionTool` wrappers needed.

## 7. Linting & Formatting

```toml
# pyproject.toml
[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

Before committing, both must pass clean:

```bash
ruff check agent.py
ruff format --check agent.py
```

Or use taskipy shortcuts from the `adk/` directory:

```bash
task lint
task format
```

No per-file ignores for line length. If a line exceeds 88 characters, break it.
