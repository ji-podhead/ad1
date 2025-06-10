-- Example SQL for initial database setup

CREATE TABLE emails (
    id SERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    body TEXT NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT NOW(),
    label TEXT,
    type TEXT,
    short_description TEXT DEFAULT NULL,
    document_ids INTEGER[] DEFAULT '{}'
);

CREATE TABLE audit_trail (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    action TEXT NOT NULL,
    username TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    roles TEXT[] NOT NULL DEFAULT '{}',
    google_id TEXT, -- Added for Google OAuth
    google_access_token TEXT NOT NULL DEFAULT 'none', -- Added for storing Google OAuth access tokens
    google_refresh_token TEXT NOT NULL DEFAULT 'none' -- Added for storing Google OAuth refresh tokens
);

CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    status TEXT NOT NULL DEFAULT 'pending', -- e.g., pending, processing, completed, failed
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    workflow_type TEXT
);

-- Trigger function to update 'updated_at' timestamp
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to 'tasks' table
CREATE TRIGGER update_tasks_modtime
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

CREATE TABLE scheduler_tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    nextRun TEXT, -- Consider TIMESTAMP WITH TIME ZONE
    to_email TEXT, -- 'to' in Pydantic model
    subject TEXT,
    body TEXT,
    date_val TEXT, -- 'date' in Pydantic model
    interval_seconds INTEGER, -- 'interval' in Pydantic model
    condition TEXT,
    actionDesc TEXT,
    trigger_type TEXT,
    workflow_config JSONB,
    workflow_name TEXT
);

-- New table for Email Types
CREATE TABLE email_types (
    id SERIAL PRIMARY KEY,
    topic TEXT UNIQUE NOT NULL,
    description TEXT
);

-- New table for Key Features
CREATE TABLE key_features (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Table to store general settings like email grabber frequency
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Optional: Insert a default setting for email grabber frequency
INSERT INTO settings (key, value) VALUES ('email_grabber_frequency_type', 'days');
INSERT INTO settings (key, value) VALUES ('email_grabber_frequency_value', '1');

INSERT INTO emails (subject, sender, body, label)
VALUES (
  'Sick Note Example',
  'doctor@clinic.ch',
  'https://m.media-amazon.com/images/I/61QnQn6YwGL._AC_SL1200_.jpg',
  'sick-note-demo'
);

-- --- DOCUMENTS TABLE (unified for raw/processed) ---
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(255),
    data_b64 TEXT, -- Base64 encoded file content
    processed_data TEXT, -- Store processed data, e.g., extracted text or summary
    is_processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
