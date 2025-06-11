# Website Login and Email Checker Flow Diagrams

This document outlines the different flows involved in user authentication and email processing within the system.

## 1. Website Login Flow

This diagram illustrates the sequence of events when a user accesses the website and logs in.

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Database

    User->>Frontend: Accesses Website
    Frontend->>Backend: GET /api/oauth-config (Fetch Google Client ID)
    Backend-->>Frontend: Google Client ID
    Frontend->>User: Displays Login Page (with Google Login Button)
    User->>Frontend: Clicks Google Login
    Frontend->>Google: Initiates OAuth Flow
    Google-->>User: Google Auth Dialog
    User->>Google: Authenticates
    Google-->>Frontend: Auth Code
    Frontend->>Backend: POST /oauth2callback (sends auth code, state with user_id)
    Backend->>Google: Exchanges Auth Code for Tokens
    Google-->>Backend: Access Token, Refresh Token
    Backend->>Database: db_utils.update_user_google_tokens_db (user_id, access_token, refresh_token)
    Database-->>Backend: Tokens Stored
    Backend->>Database: db_utils.get_user_by_id_db (user_id)
    Database-->>Backend: User Details
    Backend-->>Frontend: Login Success (e.g., JWT token, user info)
    Frontend->>User: Displays Dashboard / Inbox
```

**Key Backend Endpoints & DB Utils:**

*   **Backend API:**
    *   `GET /api/oauth-config`: Provides OAuth client details to the frontend.
    *   `POST /oauth2callback`: Handles the OAuth callback from Google, exchanges code for tokens.
    *   (Implicit) `/api/userinfo` or similar might be called by frontend post-login to fetch user details if not returned by `/oauth2callback`.
*   **`db_utils.py` functions:**
    *   `update_user_google_tokens_db`: Stores or updates the user's Google OAuth tokens.
    *   `get_user_by_id_db` (or `get_user_by_email_db`): Retrieves user information after successful authentication.

## 2. Login Flow - Main Email Not Shown

This diagram illustrates a general login verification and dashboard loading scenario, without focusing on displaying a specific email's content immediately.

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Database

    User->>Frontend: Already has session (e.g., JWT) or completes login (Simplified from Diagram 1)
    Frontend->>Backend: GET /api/userinfo (sends JWT or session token)
    Backend->>Database: db_utils.get_user_by_email_db (or by ID from token)
    Database-->>Backend: User Details (roles, permissions)
    Backend-->>Frontend: User Info (is_admin, roles)
    Frontend->>User: Displays Personalized Dashboard / Inbox View (not specific email content yet)
    User->>Frontend: Navigates to Inbox/Emails list
    Frontend->>Backend: GET /api/emails
    Backend->>Database: db_utils.get_emails_db
    Database-->>Backend: List of Emails
    Backend-->>Frontend: Emails List
    Frontend->>User: Displays list of emails
```

**Key Backend Endpoints & DB Utils:**

*   **Backend API:**
    *   `GET /api/userinfo`: Verifies user session and fetches basic user data.
    *   `GET /api/emails`: Fetches the list of emails for the user.
*   **`db_utils.py` functions:**
    *   `get_user_by_email_db` (or `get_user_by_id_db`): Retrieves user information for authentication/authorization.
    *   `get_emails_db`: Retrieves all emails for the user's inbox view.

## 3. Email Checker Workflow

This diagram details how the `email_checker` agent processes new emails.

```mermaid
sequenceDiagram
    participant Scheduler
    participant EmailCheckerAgent
    participant GmailAPI
    participant Backend
    participant Database

    Scheduler->>EmailCheckerAgent: Triggers check_new_emails job (e.g., cron)
    EmailCheckerAgent->>Database: db_utils.get_user_access_token_db (for a user with Gmail access)
    Database-->>EmailCheckerAgent: Google Access Token
    EmailCheckerAgent->>GmailAPI: Fetch new emails (using access token)
    GmailAPI-->>EmailCheckerAgent: New Email Data (subject, sender, body, attachments)

    loop For each new email
        EmailCheckerAgent->>Database: db_utils.find_existing_email_db(subject, sender, body)
        Database-->>EmailCheckerAgent: Existing Email ID or None

        alt Email is a duplicate
            EmailCheckerAgent->>Database: db_utils.delete_email_and_audit_for_duplicate_db(id) (if configured to delete)
            EmailCheckerAgent->>Logging: Logs duplicate
        else Email is new
            EmailCheckerAgent->>Database: db_utils.insert_new_email_db(subject, sender, body, received_at, ...)
            Database-->>EmailCheckerAgent: New Email ID (email_id)

            opt Attachments present
                loop For each attachment
                    EmailCheckerAgent->>GmailAPI: Fetch attachment data
                    GmailAPI-->>EmailCheckerAgent: Attachment (filename, content_type, data_b64)
                    EmailCheckerAgent->>Database: db_utils.insert_document_db(email_id, filename, content_type, data_b64, ...)
                    Database-->>EmailCheckerAgent: Document ID (doc_id)
                    EmailCheckerAgent->>EmailCheckerAgent: Collects doc_id
                end
                EmailCheckerAgent->>Database: db_utils.update_email_document_ids_db(email_id, [doc_ids])
            end

            EmailCheckerAgent->>Database: db_utils.fetch_active_workflows_db(trigger_type='email_received')
            Database-->>EmailCheckerAgent: Active Workflows list
            loop For each active workflow applicable
                EmailCheckerAgent->>Database: db_utils.create_processing_task_db(email_id, initial_status='new', workflow_type=workflow.name)
                Database-->>EmailCheckerAgent: New Task ID
                EmailCheckerAgent->>Logging: Logs task creation for workflow
            end
        end
    end
```

**Key `db_utils.py` functions:**

*   `get_user_access_token_db`: To get credentials for accessing Gmail.
*   `find_existing_email_db`: Checks if an email has already been processed.
*   `delete_email_and_audit_for_duplicate_db`: Handles duplicate emails.
*   `insert_new_email_db`: Saves new email metadata to the database.
*   `insert_document_db`: Saves email attachments to the database.
*   `update_email_document_ids_db`: Links saved documents to their parent email.
*   `fetch_active_workflows_db`: Retrieves workflow configurations that should be triggered by new emails.
*   `create_processing_task_db`: Creates a new task in the `tasks` table for each relevant workflow to process the email.

**Key Backend Components:**

*   `agent.email_checker.check_new_emails`: The core function orchestrating this flow.
*   `AgentScheduler`: Triggers the `check_new_emails` job.
