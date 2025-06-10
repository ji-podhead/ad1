# Email Data Handling

This document describes the structure of email data as retrieved from the Gmail API, how it's processed into a JSON format, stored in the database, and how it can be accessed via an API.

## Email JSON Structure

The email data is fetched from the Gmail API and processed into a JSON object. Below is an example and explanation of its key fields.

**Example Snippet (from a processed Gmail API response):**

```json
{
    "id": "1974a69b8996cddc",
    "threadId": "1974a69a7453e1cb",
    "snippet": "<body>",
    "payload": {
        "partId": "",
        "mimeType": "multipart/alternative",
        "filename": "",
        "headers": [
            {"name": "Subject", "value": "test5"},
            {"name": "From", "value": "Leonardo J. <leo@orchestra-nexus.com>"},
            {"name": "To", "value": "Leonardo J. <leo@orchestra-nexus.com>"}
        ],
        "body": {"size": 0},
        "parts": [
            {
                "partId": "0",
                "mimeType": "text/plain",
                "filename": "",
                "headers": [{"name": "Content-Type", "value": "text/plain; charset=\"UTF-8\""}],
                "body": {
                    "size": 23,
                    "data": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhDQo="
                }
            },
            {
                "partId": "1",
                "mimeType": "text/html",
                "filename": "",
                "headers": [{"name": "Content-Type", "value": "text/html; charset=\"UTF-8\""}],
                "body": {
                    "size": 44,
                    "data": "PGRpdiBkaXI9Imx0ciI-YWFhYWFhYWFhYWFhYWFhYWFhYWFhPC9kaXY-DQo="
                }
            }
        ]
    },
    "sizeEstimate": 587,
    "internalDate": "1749300131000",
    "headers": {
        "Subject": "test5",
        "From": "Leonardo J. <leo@orchestra-nexus.com>"
    },
    "body": "<body>\r\n",
    "attachments": []
}
```

**Key Fields Explanation:**

*   `id` (String): The unique Gmail message ID.
*   `threadId` (String): The ID of the email thread this message belongs to.
*   `snippet` (String): A short snippet of the email content provided by Gmail.
*   `payload` (Object): Contains the detailed structure of the email.
    *   `mimeType` (String): The MIME type of the message (e.g., `multipart/alternative`, `text/plain`).
    *   `headers` (Array): A list of header objects, each with a `name` and `value`. Important headers include `Subject`, `From`, `To`, `Date`, `Message-ID`, and `Content-Type`.
    *   `parts` (Array of Objects): If the email is `multipart` (common), this array holds the different parts of the email (e.g., plain text version, HTML version, attachments).
        *   Each part has its own `mimeType`, `headers`, and `body`.
        *   The `body` object within a part (e.g., a `text/plain` part) contains:
            *   `size` (Integer): The size of this part's body in bytes.
            *   `data` (String): The **Base64 encoded** content of this part. This needs to be decoded to get the readable text or binary data.
*   `internalDate` (String): Timestamp (milliseconds since epoch) indicating when the message was received by Gmail's server.
*   `headers` (Object): A key-value mapping of the primary email headers, extracted from `payload.headers` for easier access.
*   `body` (String): This field is populated by our application after processing the `payload`. It contains the **decoded, plain text content** of the email.
    *   The application logic prioritizes the `text/plain` part of a `multipart/alternative` email. If `text/plain` is not available, it falls back to `text/html` (which would then contain HTML markup).
    *   This field provides direct access to the readable email content without needing to manually parse the `payload.parts` and decode Base64 data.
*   `attachments` (Array of Objects): If the email has attachments that are processed by the application, this array will be populated with objects, each representing an attachment. An attachment object typically includes:
    *   `filename` (String): The name of the attached file.
    *   `mimeType` (String): The MIME type of the attachment.
    *   `data` (Bytes/String): The actual attachment data (potentially Base64 encoded if stored as a string in some intermediate JSON representations, but often handled as bytes in the application).

## Database Storage

Processed email information is stored in the `emails` table in the PostgreSQL database.

**SQL Insert Statement:**

```sql
INSERT INTO emails (subject, sender, body, received_at, label, type, short_description)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id;
```

**Mapping JSON fields to Database Columns:**

*   `subject` (TEXT): Populated from the `Subject` header in the JSON (e.g., `json.headers.Subject`).
*   `sender` (TEXT): Populated from the `From` header in the JSON (e.g., `json.headers.From`). The application extracts the email address from a string like "Display Name <email@example.com>".
*   `body` (TEXT): Populated from the processed `body` field of the JSON, which contains the decoded plain text content.
*   `received_at` (TIMESTAMP WITHOUT TIME ZONE): Currently, this is set to the timestamp when the email is processed by the application (`datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)`), not the actual `internalDate` from Gmail.
*   `label` (TEXT, nullable): A custom label that can be applied by the application (e.g., for categorization or workflow status). Defaults to `None` if not specified.
*   `type` (TEXT, nullable): The category or type assigned to the email, often by an LLM (e.g., "Important", "Marketing", "Spam"). This corresponds to the `topic` in the application logic.
*   `short_description` (TEXT, nullable): A brief summary of the email content, often generated by an LLM.

**Example Values for Insert:**

```
$1 = "test5" (Subject)
$2 = "leo@orchestra-nexus.com" (Sender)
$3 = "<body>\r\n" (Body)
$4 = '2025-06-10 10:00:00' (Timestamp of processing)
$5 = NULL (Default Label)
$6 = "Test Category" (Type/Topic from LLM)
$7 = "This is a short summary of email test5." (Short description from LLM)
```

## API Access

While specific API endpoints depend on the backend implementation, here are conceptual examples:

**1. Get a specific email by its database ID:**

*   **Request:** `GET /api/emails/{database_email_id}`
*   **Response (Success - 200 OK):**
    ```json
    {
        "id": 123,
        "subject": "test5",
        "sender": "leo@orchestra-nexus.com",
        "body": "<body>\r\n",
        "received_at": "2025-06-10T10:00:00Z",
        "label": null,
        "type": "Test Category",
        "short_description": "This is a short summary of email test5.",
        "document_ids": [10, 11]
    }
    ```

**2. List/Search emails (example with query parameters):**

*   **Request:** `GET /api/emails?sender=leo@orchestra-nexus.com&type=Test%20Category`
*   **Response (Success - 200 OK):**
    ```json
    {
        "count": 1,
        "results": [
            {
                "id": 123,
                "subject": "test5",
                "sender": "leo@orchestra-nexus.com",
                "body": "<body>\r\n",
                "received_at": "2025-06-10T10:00:00Z",
                "label": null,
                "type": "Test Category",
                "short_description": "This is a short summary of email test5."
            }
        ]
    }
    ```
