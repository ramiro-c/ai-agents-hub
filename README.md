# 🤖 AI Agents Hub

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-2.2.0-4285F4.svg)](https://google.github.io/adk-docs/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react)](https://react.dev/)

Monorepo de agentes de IA — experimentos con [Google ADK](https://google.github.io/adk-docs/) y [LangGraph](https://langchain-ai.github.io/langgraph/), y aplicaciones completas.

## 📖 Propósito

Este monorepo es un laboratorio de aprendizaje y experimentación con agentes de IA. Cada subdirectorio explora diferentes frameworks y patrones — desde agentes simples con Google ADK hasta flujos con LangGraph y aplicaciones full-stack. La meta es tener ejemplos funcionales, bien documentados, que sirvan como referencia para construir sistemas basados en agentes.

## 📁 Estructura

```
ai-agents-hub/
├── adk/                          # Agentes con Google ADK
│   ├── my_first_agent/           #   LlmAgent básico con Gemini (tutor de álgebra)
│   ├── my_config_agent/          #   Agente configurado por YAML (sin Python, tutor de álgebra)
│   ├── problem_solver/           #   PlanReActPlanner vía LiteLLM + OpenRouter
│   ├── product_extractor/        #   output_schema + Pydantic para extracción estructurada
│   ├── research_assistant/       #   Google Search integrado como herramienta built-in
│   ├── geography_assistant/      #   MCP filesystem para leer y listar archivos
│   ├── math_assistant/           #   BuiltInCodeExecutor para cálculos y análisis
│   ├── programmatic_agent.py     #   Runner + InMemorySessionService (sin CLI)
│   └── README.md                 #   Documentación detallada de los 9 agentes y patrones ADK
│
├── langgraph/                    # Experimentos con LangGraph
│   ├── lesson2.ipynb             #   Email Assistant (clasificación, draft, scheduling)
│   └── README.md                 #   Setup y descripción de notebooks
│
├── customer-support-chat/        # App full-stack de soporte al cliente con ADK
│   ├── agent/                    #   Agente ADK (Alex Chen, soporte en español, 9º agente)
│   ├── backend/                  #   Proxy FastAPI entre el frontend y ADK
│   ├── frontend/                 #   UI de chat en React + TypeScript
│   └── scripts/dev.sh            #   Levanta los tres procesos en paralelo
│
├── docs/
│   └── architecture.md           # Racional del monorepo, ADK vs LangGraph, LiteLLM/OpenRouter
│
├── .pre-commit-config.yaml       # Ruff lint + format en todos los .py
├── pyproject.toml                # Configuración de Ruff compartida
└── CONTRIBUTING.md               # Guía para contribuir al proyecto
```

> 📖 **Documentación por subproyecto**: [ADK →](adk/README.md) &nbsp;|&nbsp; [LangGraph →](langgraph/README.md) &nbsp;|&nbsp; [Customer Support Chat →](customer-support-chat/README.md) &nbsp;|&nbsp; [Arquitectura →](docs/architecture.md) &nbsp;|&nbsp; [Contribuir →](CONTRIBUTING.md)

## 🚀 Cómo ejecutar

### ADK (Google Agent Development Kit)

Cada agente en `adk/` es un directorio independiente que se ejecuta con el CLI de ADK:

```bash
cd adk
source .venv/bin/activate

# Modo interactivo
adk run problem_solver

# Modo no interactivo (replay)
echo '{"state": {}, "queries": ["What is 2+2?"]}' | adk run --replay /dev/stdin problem_solver

# Web UI
adk web problem_solver
```

Para más detalles sobre cada agente y el patrón ADK que demuestra, consultá [adk/README.md](adk/README.md).

### LangGraph

```bash
cd langgraph
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Abrir `lesson2.ipynb` en Jupyter Notebook o VS Code. El notebook construye un asistente de email que clasifica mensajes (responder, ignorar, notificar) usando `StateGraph`, `Command` routing y herramientas con `@tool`.

Ver [langgraph/README.md](langgraph/README.md) para instrucciones detalladas.

### Customer Support Chat

App full-stack con tres procesos cooperando:

```
Browser (React :5173) → Vite proxy → FastAPI (:8080) → ADK api_server (:8000) → OpenRouter LLM
```

```bash
cd customer-support-chat
cp .env.example agent/.env   # agregar OPENROUTER_API_KEY
./scripts/dev.sh              # levanta los tres procesos
```

## 🧪 Testing

Actualmente el proyecto usa verificación manual:

- **Lint y formato**: Ruff vía pre-commit hooks se ejecuta en cada `git commit`
- **Agentes ADK**: `adk run <agent>` para prueba interactiva, `adk web <agent>` para inspección visual
- **LangGraph**: Ejecutar `lesson2.ipynb` paso a paso en Jupyter/VS Code

No hay suite de tests automatizados todavía — es una contribución bienvenida. Para más contexto, ver [CONTRIBUTING.md](CONTRIBUTING.md) y [docs/architecture.md](docs/architecture.md).

## 🔧 Pre-commit hooks

Los hooks de Ruff se ejecutan automáticamente en cada `git commit`:

- **lint**: `ruff check --fix` — corrige errores automáticos
- **format**: `ruff format` — formatea el código

Para instalarlos:

```bash
adk/.venv/bin/pre-commit install
```

Para correrlos manualmente:

```bash
adk/.venv/bin/pre-commit run --all-files
```

## 📦 Dependencias

Cada subdirectorio tiene su propio entorno:

| Directorio              | Runtime                                      |
| ----------------------- | -------------------------------------------- |
| `adk/`                  | Python 3.13, google-adk 2.2.0, LiteLLM       |
| `langgraph/`            | Python 3.13, langchain ≥0.3, langgraph ≥0.4  |
| `customer-support-chat` | Python 3 (agent + backend) + Node (frontend) |

## 🤝 Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para guía de setup, hooks de pre-commit, convenciones de branches y PRs.
