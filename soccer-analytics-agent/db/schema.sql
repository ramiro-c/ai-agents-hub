CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INT,
    away_score INT,
    tournament TEXT,
    city TEXT,
    country TEXT,
    neutral BOOLEAN
);

CREATE TABLE IF NOT EXISTS goalscorers (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    team TEXT,
    scorer TEXT,
    minute INT,
    own_goal BOOLEAN,
    penalty BOOLEAN
);

CREATE TABLE IF NOT EXISTS shootouts (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    winner TEXT,
    first_shooter TEXT
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches (match_date);
CREATE INDEX IF NOT EXISTS idx_matches_home ON matches (home_team);
CREATE INDEX IF NOT EXISTS idx_matches_away ON matches (away_team);
CREATE INDEX IF NOT EXISTS idx_goalscorers_scorer ON goalscorers (scorer);

-- --- Memory tables (Phase 2) ---

CREATE TABLE IF NOT EXISTS working_memory (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_working_session
    ON working_memory (session_id, created_at);

CREATE TABLE IF NOT EXISTS episodic_memory (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    agent_response TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_episodic_embedding
    ON episodic_memory USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS semantic_memory (
    id BIGSERIAL PRIMARY KEY,
    fact TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_semantic_embedding
    ON semantic_memory USING hnsw (embedding vector_cosine_ops);