-- Example SQL for initial database setup

CREATE TABLE emails (
    id SERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    body TEXT NOT NULL,
    label TEXT
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
    roles TEXT[] NOT NULL DEFAULT '{}'
);

INSERT INTO emails (subject, sender, body, label)
VALUES (
  'Sick Note Example',
  'doctor@clinic.ch',
  'https://m.media-amazon.com/images/I/61QnQn6YwGL._AC_SL1200_.jpg',
  'sick-note-demo'
);
