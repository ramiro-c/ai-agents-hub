# Architecture (finished state)

How the agent works once all phases are complete. These diagrams describe the
*target* system (Phases 0–8), not necessarily what is implemented today — see
`../CONTEXT.md` for current status.

## 1. System overview

```mermaid
flowchart TB
    subgraph client["Client"]
        UI["React UI"]
        CLI["CLI REPL"]
    end

    subgraph runrt["Cloud Run container"]
        API["FastAPI<br/>/chat /predict /health /memory /trace"]
        RESP["respond() — memory-aware wrapper"]
        LOOP["run_turn — hand-written tool loop"]
        TOOLS["tools<br/>sql_query, hybrid_retrieve, vector_search,<br/>predict_match, get_elo, remember, recall"]
        MINI["MiniLM embedder<br/>baked into image"]
        XGB["XGBoost predictor<br/>baked into image"]
    end

    GEM["Gemini via Vertex AI"]

    subgraph pg["Cloud SQL — Postgres + pgvector"]
        T1["matches / goalscorers / shootouts"]
        T2["match_documents<br/>embedding + tsv"]
        T3["working / episodic / semantic memory"]
        T4["agent_trace"]
    end

    UI --> API
    CLI --> RESP
    API --> RESP
    RESP --> LOOP
    LOOP <--> GEM
    LOOP --> TOOLS
    TOOLS --> MINI
    TOOLS --> XGB
    TOOLS --> pg
    RESP --> T3
    LOOP --> T4
```

## 2. One turn, end to end

```mermaid
sequenceDiagram
    actor U as User
    participant R as respond()
    participant M as Memory (Postgres)
    participant L as run_turn
    participant G as Gemini
    participant T as Tools

    U->>R: question
    R->>M: load working + recall episodic
    M-->>R: recent turns + relevant episodes
    R->>L: seeded history + grounded question

    loop until the model answers in text
        L->>G: history + tool declarations
        G-->>L: function_call(s) OR text
        alt tool call(s)
            L->>T: dispatch(name, args)
            T-->>L: result (or error-as-result)
            L->>M: log step to agent_trace
        end
    end

    L-->>R: final answer
    R->>M: persist working + episodic
    R-->>U: answer
```

## 3. Which tool? (the model decides by question shape)

```mermaid
flowchart TD
    Q["User question"] --> D{"What shape is it?"}
    D -->|"exact / structured / aggregate"| SQL["sql_query<br/>precise, complete, verifiable"]
    D -->|"fuzzy / semantic / no clean WHERE"| HR["hybrid_retrieve<br/>meaning-based recall"]
    D -->|"who will win / prediction"| PM["predict_match<br/>XGBoost specialist"]
    D -->|"something the user told me before"| RC["recall / remember<br/>semantic memory"]

    SQL --> A["Gemini composes the final answer"]
    HR --> A
    PM --> A
    RC --> A
```

## 4. Hybrid retrieval internals (Phase 3)

```mermaid
flowchart LR
    Q["query text"] --> E["MiniLM embed"]
    Q --> TS["websearch_to_tsquery"]

    E --> V["vector search<br/>cosine distance, HNSW index"]
    TS --> F["full-text search<br/>tsv match, GIN index"]

    V --> RRF["RRF fuse<br/>score = sum 1 / (k + rank)"]
    F --> RRF
    RRF --> TOP["top-k match documents"]
```

## 5. Three-tier memory

```mermaid
flowchart TB
    subgraph turn["Every turn, respond() handles"]
        W["Working memory<br/>recency, this session<br/>seeded into history"]
        EP["Episodic memory<br/>similarity, this session<br/>injected as grounding"]
    end
    subgraph model["The model controls via tools"]
        S["Semantic memory<br/>similarity, global facts<br/>remember() / recall()"]
    end

    W -->|"last N turns"| LOOP2["run_turn"]
    EP -->|"relevant past moments"| LOOP2
    LOOP2 -->|"the model may store/fetch facts"| S
```
