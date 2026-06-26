# Contributing to AI Agents Hub

Thanks for contributing. This guide covers setup, conventions, and tooling.

## Environment Setup

```bash
# Clone and enter the repo
git clone <repo-url> && cd ai-agents-hub

# ADK agents
cd adk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# LangGraph experiments
cd ../langgraph
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Customer Support Chat (agent + backend + frontend)
cd ../customer-support-chat
# See customer-support-chat/README.md for full setup
```

## Pre-commit Hooks

Ruff lint and format run automatically on every `git commit`:

- **lint**: `ruff check --fix` — catches and auto-fixes issues
- **format**: `ruff format` — enforces consistent style

### Install Hooks

```bash
# From the repo root
adk/.venv/bin/pre-commit install
```

Manual run (without committing):

```bash
adk/.venv/bin/pre-commit run --all-files
```

### Ruff Configuration

See `pyproject.toml` at the repo root:
- Line length: 88
- Rules: `E` (errors), `F` (pyflakes), `I` (import sorting)
- Double quotes, space indentation
- Notebooks (`.ipynb`) excluded from linting

## Branch Naming

| Prefix | Purpose |
|--------|---------|
| `feat/` | New agent, feature, or capability |
| `docs/` | Documentation changes (READMEs, architecture) |
| `fix/` | Bug fixes |
| `refactor/` | Code restructuring without behavior change |
| `chore/` | Tooling, dependencies, pre-commit config |

Examples: `feat/add-research-agent`, `docs/update-readme-agents`, `fix/auth-middleware-typo`

## Pull Requests

- **Size**: Keep PRs focused. If a change touches more than 5 files or 400 lines, consider splitting.
- **Description**: Explain *what* changed and *why*. Reference related issues if applicable.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:` prefix.
- **Pre-commit**: Hooks must pass before pushing. Run manually if unsure:

```bash
adk/.venv/bin/pre-commit run --all-files
```

## Adding a New Agent

1. Create a directory under `adk/<agent_name>/`
2. Add `agent.py` (or `root_agent.yaml`) and any required `__init__.py`
3. Test with `adk run <agent_name>` or `adk web <agent_name>`
4. **Update `adk/README.md`** — add your agent under the matching pattern category. Include agent name, pattern demonstrated, and a one-line description.
5. **Update root `README.md`** — add your agent to the directory tree and describe it briefly.

### Docs Drift Prevention

> **Reminder**: When you add, rename, or remove an agent, update both `README.md` (root) and `adk/README.md`. Stale documentation is worse than no documentation.

## Code Style

- Follow existing patterns in `adk/` — look at `my_first_agent/agent.py` for the simplest example
- Use `LlmAgent` (not the deprecated `Agent` alias) for new agents
- Keep agents self-contained: one directory per agent with its own configuration
- Python example agents default to Gemini unless they demonstrate a specific model feature (e.g., OpenRouter for non-Gemini planning)
- Spanish content in `customer-support-chat/` is intentional — preserve it

## Testing

This project currently uses manual verification:
- `adk run <agent>` — interactive agent testing
- `adk web <agent>` — web UI testing
- Ruff lint + format via pre-commit

Automated test infrastructure is a welcome contribution. See `docs/architecture.md` for context on current testing strategy.

## Questions?

- Architecture decisions: [`docs/architecture.md`](docs/architecture.md)
- Agent patterns: [`adk/README.md`](adk/README.md)
- LangGraph setup: [`langgraph/README.md`](langgraph/README.md)
- Full-stack app: [`customer-support-chat/README.md`](customer-support-chat/README.md)
