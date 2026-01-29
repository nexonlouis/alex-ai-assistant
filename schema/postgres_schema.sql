-- PostgreSQL Schema for Alex AI Assistant
-- Migrated from Neo4j to PostgreSQL with pgvector
-- Version: 1.0.0

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Time tree (denormalized for efficiency)
-- Replaces Neo4j's Year→Month→Week→Day hierarchy
CREATE TABLE IF NOT EXISTS days (
    date DATE PRIMARY KEY,
    year INT NOT NULL,
    month INT NOT NULL,
    day INT NOT NULL,
    week_number INT NOT NULL,
    day_of_week INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Interactions (core memory - replaces Neo4j Interaction nodes)
CREATE TABLE IF NOT EXISTS interactions (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    date DATE REFERENCES days(date) ON DELETE SET NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    intent VARCHAR(50),
    complexity_score FLOAT DEFAULT 0.0,
    model_used VARCHAR(100),
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Concepts (replaces Neo4j Concept nodes)
CREATE TABLE IF NOT EXISTS concepts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    normalized_name VARCHAR(255),
    first_mentioned TIMESTAMPTZ DEFAULT NOW(),
    mention_count INT DEFAULT 0
);

-- Interaction-Concept junction (replaces MENTIONS_CONCEPT relationship)
CREATE TABLE IF NOT EXISTS interaction_concepts (
    interaction_id VARCHAR(255) REFERENCES interactions(id) ON DELETE CASCADE,
    concept_id INT REFERENCES concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (interaction_id, concept_id)
);

-- =============================================================================
-- SUMMARY TABLES
-- =============================================================================

-- Daily summaries (replaces Neo4j DailySummary nodes)
CREATE TABLE IF NOT EXISTS daily_summaries (
    date DATE PRIMARY KEY REFERENCES days(date) ON DELETE CASCADE,
    content TEXT NOT NULL,
    key_topics TEXT[],
    interaction_count INT DEFAULT 0,
    model_used VARCHAR(100),
    embedding vector(768),
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Weekly summaries (replaces Neo4j WeeklySummary nodes)
CREATE TABLE IF NOT EXISTS weekly_summaries (
    week_id VARCHAR(10) PRIMARY KEY,  -- YYYY-Wxx format
    year INT NOT NULL,
    week INT NOT NULL,
    content TEXT NOT NULL,
    key_themes TEXT[],
    daily_summary_count INT DEFAULT 0,
    total_interactions INT DEFAULT 0,
    model_used VARCHAR(100),
    embedding vector(768),
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Monthly summaries (replaces Neo4j MonthlySummary nodes)
CREATE TABLE IF NOT EXISTS monthly_summaries (
    month_id VARCHAR(10) PRIMARY KEY,  -- YYYY-M format
    year INT NOT NULL,
    month INT NOT NULL,
    content TEXT NOT NULL,
    key_themes TEXT[],
    weekly_summary_count INT DEFAULT 0,
    total_interactions INT DEFAULT 0,
    model_used VARCHAR(100),
    embedding vector(768),
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- CODE CHANGE TRACKING
-- =============================================================================

-- Code changes (self-modification tracking - replaces Neo4j CodeChange nodes)
CREATE TABLE IF NOT EXISTS code_changes (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    date DATE REFERENCES days(date) ON DELETE SET NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    files_modified TEXT[] NOT NULL,
    description TEXT NOT NULL,
    reasoning TEXT,
    change_type VARCHAR(50),
    commit_sha VARCHAR(40),
    related_interaction_id VARCHAR(255) REFERENCES interactions(id) ON DELETE SET NULL,
    file_count INT GENERATED ALWAYS AS (cardinality(files_modified)) STORED
);

-- Code change concepts junction (replaces MODIFIES_CONCEPT relationship)
CREATE TABLE IF NOT EXISTS code_change_concepts (
    change_id VARCHAR(255) REFERENCES code_changes(id) ON DELETE CASCADE,
    concept_id INT REFERENCES concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (change_id, concept_id)
);

-- =============================================================================
-- PROJECTS (for related projects lookup)
-- =============================================================================

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date);
CREATE INDEX IF NOT EXISTS idx_interactions_intent ON interactions(intent);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);
CREATE INDEX IF NOT EXISTS idx_concepts_normalized ON concepts(normalized_name);
CREATE INDEX IF NOT EXISTS idx_code_changes_date ON code_changes(date);
CREATE INDEX IF NOT EXISTS idx_code_changes_type ON code_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_code_changes_timestamp ON code_changes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_days_year_month ON days(year, month);
CREATE INDEX IF NOT EXISTS idx_days_week ON days(year, week_number);

-- Full-text search indexes for concept name lookups
CREATE INDEX IF NOT EXISTS idx_concepts_name_trgm ON concepts USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_projects_name_trgm ON projects USING gin (name gin_trgm_ops);

-- Vector indexes (HNSW for fast approximate nearest neighbor search)
-- Using cosine distance (vector_cosine_ops) to match Neo4j's cosine similarity
CREATE INDEX IF NOT EXISTS idx_interactions_embedding ON interactions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_daily_summaries_embedding ON daily_summaries
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_weekly_summaries_embedding ON weekly_summaries
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_monthly_summaries_embedding ON monthly_summaries
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for users table
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VIEWS FOR COMMON QUERIES
-- =============================================================================

-- View for interactions with their concepts
CREATE OR REPLACE VIEW interactions_with_concepts AS
SELECT
    i.*,
    array_agg(c.name) FILTER (WHERE c.name IS NOT NULL) AS concept_names
FROM interactions i
LEFT JOIN interaction_concepts ic ON i.id = ic.interaction_id
LEFT JOIN concepts c ON ic.concept_id = c.id
GROUP BY i.id;

-- View for daily stats
CREATE OR REPLACE VIEW daily_stats AS
SELECT
    d.date,
    d.year,
    d.month,
    d.day,
    d.week_number,
    COUNT(i.id) AS interaction_count,
    CASE WHEN ds.date IS NOT NULL THEN true ELSE false END AS has_summary
FROM days d
LEFT JOIN interactions i ON d.date = i.date
LEFT JOIN daily_summaries ds ON d.date = ds.date
GROUP BY d.date, d.year, d.month, d.day, d.week_number, ds.date;

-- =============================================================================
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE users IS 'Users who interact with Alex';
COMMENT ON TABLE days IS 'Denormalized time tree for efficient temporal queries';
COMMENT ON TABLE interactions IS 'Core memory: all user-assistant interactions';
COMMENT ON TABLE concepts IS 'Extracted concepts/topics from interactions';
COMMENT ON TABLE daily_summaries IS 'Daily summaries of interactions';
COMMENT ON TABLE weekly_summaries IS 'Weekly aggregated summaries';
COMMENT ON TABLE monthly_summaries IS 'Monthly strategic summaries';
COMMENT ON TABLE code_changes IS 'Self-modification tracking for Alex';
COMMENT ON TABLE projects IS 'Projects mentioned in interactions';

COMMENT ON COLUMN interactions.embedding IS '768-dimensional embedding from text-embedding-004';
COMMENT ON COLUMN daily_summaries.embedding IS '768-dimensional embedding for semantic search';
