-- OpenReplay Database Initialization
-- This script sets up the required tables for OpenReplay session storage

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    project_id SERIAL PRIMARY KEY,
    project_key VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    active BOOLEAN DEFAULT true,
    platform VARCHAR(50) DEFAULT 'web',
    sample_rate SMALLINT DEFAULT 100,
    gdpr JSONB DEFAULT '{}',
    metadata_1 VARCHAR(255),
    metadata_2 VARCHAR(255),
    metadata_3 VARCHAR(255),
    metadata_4 VARCHAR(255),
    metadata_5 VARCHAR(255),
    save_request_payloads BOOLEAN DEFAULT true
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id BIGSERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(project_id),
    tracker_version VARCHAR(20),
    rev_id VARCHAR(50),
    user_uuid VARCHAR(50),
    user_os VARCHAR(100),
    user_os_version VARCHAR(50),
    user_browser VARCHAR(100),
    user_browser_version VARCHAR(50),
    user_device VARCHAR(100),
    user_device_type VARCHAR(50),
    user_country VARCHAR(3),
    user_city VARCHAR(100),
    user_state VARCHAR(100),
    user_agent TEXT,
    user_id VARCHAR(255),
    user_anonymous_id VARCHAR(255),
    referrer TEXT,
    base_path TEXT,
    start_ts BIGINT NOT NULL,
    duration BIGINT,
    pages_count INTEGER DEFAULT 0,
    events_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    issues_score INTEGER DEFAULT 0,
    issue_types TEXT[],
    viewed BOOLEAN DEFAULT false,
    favorite BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    file_key VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Events table for custom tracking events
CREATE TABLE IF NOT EXISTS events (
    event_id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES sessions(session_id),
    message_id BIGINT,
    timestamp BIGINT NOT NULL,
    seq_index INTEGER,
    name VARCHAR(255) NOT NULL,
    payload JSONB DEFAULT '{}'
);

-- Issues table for errors and performance issues
CREATE TABLE IF NOT EXISTS issues (
    issue_id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES sessions(session_id),
    timestamp BIGINT NOT NULL,
    type VARCHAR(50) NOT NULL,
    context_string TEXT,
    context JSONB DEFAULT '{}',
    payload JSONB DEFAULT '{}'
);

-- User defined events for agent tracking
CREATE TABLE IF NOT EXISTS custom_events (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES sessions(session_id),
    timestamp BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    payload JSONB DEFAULT '{}'
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_ts ON sessions(start_ts);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_name ON events(name);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_issues_session_id ON issues(session_id);
CREATE INDEX IF NOT EXISTS idx_custom_events_session_id ON custom_events(session_id);
CREATE INDEX IF NOT EXISTS idx_custom_events_name ON custom_events(name);

-- Insert default project for Pythinker
INSERT INTO projects (project_key, name, platform)
VALUES ('pythinker-dev', 'Pythinker Development', 'web')
ON CONFLICT (project_key) DO NOTHING;
