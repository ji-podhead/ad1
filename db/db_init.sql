-- Drop existing tables (if they exist)
DROP TABLE IF EXISTS audit_trail CASCADE;
DROP TABLE IF EXISTS email_tasks CASCADE;
DROP TABLE IF EXISTS email_documents CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS emails CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Function to update 'updated_at' timestamp
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL, -- App logic should handle hashing
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    roles TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TRIGGER set_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- Emails table
CREATE TABLE emails (
    id TEXT PRIMARY KEY, -- Unique email Message-ID
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- Optional: if emails are associated with a user account
    topic TEXT,
    sender TEXT NOT NULL,
    recipient TEXT, -- Can be multiple, consider TEXT[] or separate table
    cc TEXT,
    bcc TEXT,
    subject TEXT,
    body_html TEXT,
    body_text TEXT,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL, -- When the email was originally received
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), -- When it was imported into this system
    archived BOOLEAN DEFAULT FALSE,
    read BOOLEAN DEFAULT FALSE,
    labels TEXT[] -- For user-defined labels/tags
);

-- Documents table
CREATE TABLE documents (
    id TEXT PRIMARY KEY, -- UUID for the document
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes BIGINT,
    storage_path TEXT, -- If stored on filesystem
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Email-Documents association table
CREATE TABLE email_documents (
    email_id TEXT REFERENCES emails(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (email_id, document_id)
);

-- Tasks table
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, -- UUID for the task
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- User this task is assigned to
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'todo', -- e.g., 'todo', 'in_progress', 'done', 'archived'
    priority TEXT DEFAULT 'medium', -- e.g., 'low', 'medium', 'high'
    due_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TRIGGER set_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- Email-Tasks association table
CREATE TABLE email_tasks (
    email_id TEXT REFERENCES emails(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (email_id, task_id)
);

-- Audit Trail table
CREATE TABLE audit_trail (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- Who performed the action
    email_id TEXT REFERENCES emails(id) ON DELETE SET NULL, -- Related email, if any
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL, -- Related task, if any
    action TEXT NOT NULL, -- Description of the action
    details JSONB, -- For storing arbitrary details about the action
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Example initial admin user (optional)
-- INSERT INTO users (email, password, is_admin, roles) VALUES ('admin@example.com', 'changeme', TRUE, '{"admin"}');
