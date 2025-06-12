# Database Table Overview

This document provides an overview of the key tables in the ad1 PostgreSQL database.

## emails

Stores information about ingested emails.

| Column            | Type                        | Description                                    |
|-------------------|-----------------------------|------------------------------------------------|
| `id`              | `SERIAL PRIMARY KEY`        | Unique identifier for the email.               |
| `subject`         | `VARCHAR(255)`              | Subject line of the email.                     |
| `sender`          | `VARCHAR(255)`              | Sender's email address or name.                |
| `body`            | `TEXT`                      | Full body content of the email.                |
| `received_at`     | `TIMESTAMP WITHOUT TIME ZONE` | Timestamp when the email was received/fetched. |
| `label`           | `VARCHAR(50)`               | User-assigned label for the email (e.g., 'Inbox', 'Archive'). |
| `type`            | `VARCHAR(50)`               | Automatically classified type of the email (e.g., 'Invoice', 'Support'). |
| `short_description`| `VARCHAR(255)`              | A brief summary of the email content.          |
| `document_ids`    | `INTEGER[]`                 | Array of IDs linking to associated documents (attachments). |

## documents

Stores information and content of documents attached to emails.

| Column         | Type                        | Description                                    |
|----------------|-----------------------------|------------------------------------------------|
| `id`           | `SERIAL PRIMARY KEY`        | Unique identifier for the document.            |
| `email_id`     | `INTEGER`                   | Foreign key linking to the parent email in the `emails` table. |
| `filename`     | `VARCHAR(255)`              | Original filename of the attachment.           |
| `content_type` | `VARCHAR(100)`              | MIME type of the document (e.g., 'application/pdf'). |
| `data_b64`     | `TEXT`                      | Base64 encoded content of the document.        |
| `is_processed` | `BOOLEAN`                   | Indicates if the document has been processed by an agent. |
| `created_at`   | `TIMESTAMP WITHOUT TIME ZONE` | Timestamp when the document record was created. |

## audit_trail

Logs significant actions and changes within the system for compliance and traceability.

| Column    | Type                        | Description                                    |
|-----------|-----------------------------|------------------------------------------------|
| `id`      | `SERIAL PRIMARY KEY`        | Unique identifier for the audit log entry.     |
| `email_id`| `INTEGER`                   | Optional foreign key linking to a relevant email. |
| `action`  | `TEXT`                      | Description of the action performed.           |
| `username`| `VARCHAR(255)`              | User or system process that performed the action. |
| `timestamp`| `TIMESTAMP WITHOUT TIME ZONE` | Timestamp when the action occurred.            |

## tasks

Tracks the status and progress of email and document processing workflows.

| Column        | Type                        | Description                                    |
|---------------|-----------------------------|------------------------------------------------|
| `id`          | `SERIAL PRIMARY KEY`        | Unique identifier for the task.                |
| `email_id`    | `INTEGER`                   | Foreign key linking to the associated email.   |
| `status`      | `VARCHAR(50)`               | Current status of the task (e.g., 'pending', 'processing', 'validated'). |
| `created_at`  | `TIMESTAMP WITHOUT TIME ZONE` | Timestamp when the task was created.           |
| `updated_at`  | `TIMESTAMP WITHOUT TIME ZONE` | Timestamp when the task was last updated.      |
| `workflow_type`| `VARCHAR(50)`               | The type of workflow associated with this task. |

## scheduler_tasks

Stores configurations for scheduled tasks and workflows.

| Column          | Type                        | Description                                    |
|-----------------|-----------------------------|------------------------------------------------|
| `id`            | `VARCHAR(36) PRIMARY KEY`   | Unique identifier for the scheduled task (UUID). |
| `type`          | `VARCHAR(50)`               | Type of scheduled task (e.g., 'email', 'cron', 'agent_event'). |
| `description`   | `TEXT`                      | Description of the scheduled task.             |
| `status`        | `VARCHAR(50)`               | Status of the scheduled task ('active', 'paused'). |
| `next_run_at`       | `TIMESTAMP WITHOUT TIME ZONE` | The next scheduled time for the task to run.   |
| `to_email`      | `VARCHAR(255)`              | Recipient email address (for email tasks).     |
| `subject`       | `VARCHAR(255)`              | Email subject (for email tasks).               |
| `body`          | `TEXT`                      | Email body (for email tasks).                  |
| `date_val`      | `VARCHAR(50)`               | Specific date/time for scheduling (if applicable). |
| `interval_seconds`| `INTEGER`                   | Interval in seconds for recurring tasks.       |
| `condition`     | `TEXT`                      | Semantic condition for agent events.           |
| `actionDesc`    | `TEXT`                      | Description of the action to perform.          |
| `trigger_type`  | `VARCHAR(50)`               | The type of trigger for the workflow ('email_receive', 'cron'). |
| `workflow_config`| `JSONB`                     | JSON object containing workflow-specific configuration (model, steps, etc.). ||
| `task_name` | `VARCHAR(255)`              | A user-defined name for the workflow.          |

## settings

Stores application settings.

| Column | Type           | Description                                    |
|--------|----------------|------------------------------------------------|
| `key`  | `VARCHAR(255) PRIMARY KEY` | Setting key (e.g., 'email_grabber_frequency_type'). |
| `value`| `TEXT`         | Setting value.                                 |

## users

Stores user information for authentication and authorization.

| Column               | Type                        | Description                                    |
|----------------------|-----------------------------|------------------------------------------------|
| `id`                 | `SERIAL PRIMARY KEY`        | Unique identifier for the user.                |
| `email`              | `VARCHAR(255) UNIQUE`       | User's email address (used for login).         |
| `password`           | `VARCHAR(255)`              | Hashed password.                               |
| `is_admin`           | `BOOLEAN`                   | Indicates if the user has administrative privileges. |
| `roles`              | `VARCHAR(50)[]`             | Array of user roles (e.g., ['admin', 'user']). |
| `google_id`          | `VARCHAR(255)`              | Google ID for OAuth.                           |
| `mcp_token`          | `TEXT`                      | Token for MCP server access.                   |
| `google_access_token`| `TEXT`                      | Google OAuth access token.                     |
| `google_refresh_token`| `TEXT`                      | Google OAuth refresh token.                    |
