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