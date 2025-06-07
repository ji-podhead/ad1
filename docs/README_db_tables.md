# Database Tables Overview

Below are the main tables used in the backend database, with their columns and types as inferred from the code and schema:

## `emails` (updated)
| Column           | Type                | Description                                 |
|------------------|---------------------|---------------------------------------------|
| id               | SERIAL PRIMARY KEY  | Unique email ID                             |
| subject          | TEXT                | Email subject                               |
| sender           | TEXT                | Sender email address                        |
| body             | TEXT                | Email body/content                          |
| received_at      | TIMESTAMP WITH TZ   | When the email was received                 |
| label            | TEXT (nullable)     | Optional label                              |
| type             | TEXT                | Document type (from LLM classification)     |
| short_description| TEXT                | Short summary (from LLM)                    |
| document_ids     | INTEGER[]           | List of document IDs (attachments)          |

## `audit_trail`
| Column    | Type                | Description                                 |
|-----------|---------------------|---------------------------------------------|
| id        | SERIAL PRIMARY KEY  | Unique audit entry ID                       |
| email_id  | INTEGER (nullable)  | Related email ID (if applicable)            |
| action    | TEXT                | Description of the action                   |
| username  | TEXT                | User or system that performed the action    |
| timestamp | TIMESTAMP WITH TZ   | When the action occurred                    |

## `scheduler_tasks`
| Column         | Type                | Description                                 |
|----------------|---------------------|---------------------------------------------|
| id             | SERIAL PRIMARY KEY  | Unique task ID                              |
| workflow_name  | TEXT                | Name of the workflow                        |
| workflow_config| JSONB or TEXT       | Workflow configuration (JSON)               |
| status         | TEXT                | Task status (e.g., 'active')                |
| trigger_type   | TEXT                | Trigger type (e.g., 'cron')                 |

## `tasks`
| Column        | Type                | Description                                 |
|---------------|---------------------|---------------------------------------------|
| id            | SERIAL PRIMARY KEY  | Unique task ID                              |
| email_id      | INTEGER             | Related email ID                            |
| status        | TEXT                | Task status (e.g., 'pending')               |
| created_at    | TIMESTAMP WITH TZ   | When the task was created                   |
| updated_at    | TIMESTAMP WITH TZ   | When the task was last updated              |
| workflow_type | TEXT                | Workflow type/topic                         |

## `documents`
| Column          | Type                | Description                                         |
|-----------------|---------------------|-----------------------------------------------------|
| id              | SERIAL PRIMARY KEY  | Unique document ID                                  |
| email_id        | INTEGER             | Related email ID (foreign key to emails)            |
| filename        | TEXT                | Original filename of the attachment                 |
| content_type    | TEXT                | MIME type of the document                           |
| data_b64        | TEXT (nullable)     | Base64-encoded document data (raw, if not processed)|
| processed_data  | JSONB or TEXT       | Processed/Extracted data (e.g. OCR, text, etc.)     |
| is_processed    | BOOLEAN             | True if processed, False if raw                     |
| created_at      | TIMESTAMP WITH TZ   | When the document was stored/processed              |

---

> **Note:** Column types and names are based on the backend code and may differ slightly from the actual DB schema. For the authoritative schema, see `db/db_init.sql`.
