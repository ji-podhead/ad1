# ad1 API Overview

## 1. Introduction to the API

The ad1 backend exposes a secure RESTful API that provides access to all core functionalities of the platform. This API is used by the frontend application and can also be used by other authorized client applications or services. All API endpoints require authentication (typically via Google OAuth 2.0 tokens) to ensure secure access to data and operations. The backend evaluates user roles based on the authenticated user's email and grants permissions accordingly.

## 2. General API Endpoint Summary

This section provides a high-level overview of the primary API endpoints and their functions.

-   `/api/emails`: Methods for listing, viewing details of, and labeling emails within the system.
-   `/api/documents`: Endpoints for uploading, listing, and managing the processing of documents.
-   `/api/validation`: Operations to manage human-in-the-loop validation tasks, including approving, aborting, or restarting processing tasks.
-   `/api/audit`: Allows for viewing comprehensive audit logs for system activities and compliance tracking.
-   `/ws/agent`: A WebSocket endpoint for real-time, interactive communication with the AI agent layer (e.g., Catbot for workflow orchestration).
-   `GET /api/processing_tasks`: Retrieves a list of all email processing tasks, including their current status and details from the linked email (subject, sender, received date).
-   `POST /api/processing_tasks/{task_id}/validate`: Marks a specific processing task (identified by `task_id`) as 'validated'. This is typically used after human-in-the-loop verification.
-   `POST /api/processing_tasks/{task_id}/abort`: Marks a specific processing task as 'aborted', indicating it should not proceed further.
-   `POST /api/tasks/{task_id}/status`: Allows setting an arbitrary status for a specific task.
    -   Request body: `{ "status": "new_status_value" }`

## 3. Detailed Backend API Endpoints

The following provides a more detailed breakdown of the backend API endpoints.

**Authentication Note**: All endpoints listed below require successful authentication. The backend uses the authenticated user's information (e.g., email from Google OAuth token) to determine roles (admin, user) and apply appropriate access controls.

---

### Authentication & User Information

-   `GET /api/oauth-config`
    -   **Purpose**: Returns the Google OAuth client configuration (e.g., `client_id`) required by the frontend.
    -   **Usage**: The frontend calls this endpoint during its initialization phase to obtain the necessary parameters to start the Google Login flow.

-   `POST /api/userinfo`
    -   **Purpose**: Retrieves user-specific information, including administrative status and roles.
    -   **Request Body**: `{ "email": "user@example.com", "token": "<google_id_token_optional_for_some_flows>" }`
    -   **Response**: `{ "is_admin": true/false, "roles": ["role1", "role2"], ... }`
    -   **Usage**: Called by the frontend after a successful Google login to determine the user's privileges and customize the UI accordingly.

---

### Email Management

-   `GET /api/emails`
    -   **Purpose**: Lists all emails accessible to the authenticated user within the system.

-   `GET /api/emails/{email_id}`
    -   **Purpose**: Retrieves detailed information for a specific email identified by `email_id`.

-   `POST /api/emails/{email_id}/label`
    -   **Purpose**: Sets or updates a label for a specific email.
    -   **Request Body**: `{ "label": "new_label_value" }`

-   `DELETE /api/emails/{email_id}`
    -   **Purpose**: Deletes a specific email identified by `email_id` from the system.

---

### Document Management

-   `GET /api/documents`
    -   **Purpose**: Lists all documents (e.g., attachments) accessible to the authenticated user.

-   `GET /api/documents/{document_id}/content`
    -   **Purpose**: Fetches the content of a specific document identified by `document_id`.

-   `DELETE /api/documents/{document_id}`
    -   **Purpose**: Deletes a specific document identified by `document_id`.

---

### Audit Trail

-   `GET /api/audit`
    -   **Purpose**: Retrieves the audit trail, providing logs of significant actions for compliance and traceability.

---

### User Management (Admin Only)

The following user management endpoints typically require administrator privileges.

-   `GET /api/users`
    -   **Purpose**: Lists all users in the system. (Admin only)

-   `POST /api/users/add`
    -   **Purpose**: Creates a new user account. (Admin only)
    -   **Request Body**: Requires `email` and `password`. Optional fields include `roles` (list of strings) and `is_admin` (boolean).

-   `PUT /api/users/{user_identifier}/set`
    -   **Purpose**: Updates an existing user\'s details. `user_identifier` can be the user\'s database ID or their email address. (Admin only)
    -   **Request Body**: Allows updating fields such as `email`, `password`, `roles`, or `is_admin` status.

-   `DELETE /api/users/{user_identifier}`
    -   **Purpose**: Deletes a user account. `user_identifier` can be the user\'s database ID or their email address. (Admin only)

---

### Agent Interaction (WebSocket)

-   `/ws/agent`
    -   **Purpose**: Provides a WebSocket endpoint for real-time, bi-directional communication with the backend agent layer. This is used for features like the Agent Chat to trigger workflows, ask for status updates, or interact with conversational AI components.

---

### Scheduler & Workflow Management

-   `GET /api/scheduler/tasks`
    -   **Purpose**: Lists all scheduled tasks and workflow configurations, including their full definitions (triggers, steps, parameters).

-   `POST /api/scheduler/task`
    -   **Purpose**: Creates a new scheduled task or workflow.
    -   **Request Body (Payload Example)**:
        ```json
        {
          "workflow_name": "Monthly Report Generation",
          "trigger_type": "cron", // or "email_receive"
          "cron_expression": "0 0 1 * *", // if trigger_type is cron
          "email_trigger_config": { // if trigger_type is email_receive
            "subject_contains": "Invoice",
            "from_address": "billing@example.com"
          },
          "workflow_config": {
            "model": "gpt-4",
            "tokens": 2000,
            "steps": ["step1_compliance_check", "step2_data_extraction", "step3_human_verification"],
            "initial_status": "pending_approval"
          },
          "action_parameters": { /* specific parameters for the action */ }
        }
        ```
    -   **Details**: The payload includes `workflow_name`, `trigger_type` (`email_receive`, `cron`), `workflow_config` (a JSON object detailing AI model, token limits, processing steps, initial status for created tasks), and other relevant scheduling or action parameters.

-   `POST /api/scheduler/task/{task_id}/pause`
    -   **Purpose**: Pauses or resumes a specific scheduled task or workflow identified by `task_id`.
    -   **Request Body**: `{ "paused": true/false }`

-   `DELETE /api/scheduler/task/{task_id}`
    -   **Purpose**: Deletes a specific scheduled task or workflow identified by `task_id`.

---

### Processing Task Management

These endpoints are focused on managing the state of tasks that are actively being processed or awaiting validation, often related to email processing.

-   `GET /api/processing_tasks`
    -   **Purpose**: Retrieves a list of all email processing tasks, including their current status (e.g., 'pending', 'processing', 'needs_validation', 'validated', 'aborted') and details from the linked email (subject, sender, received date).

-   `POST /api/processing_tasks/{task_id}/validate`
    -   **Purpose**: Marks a specific task (identified by `task_id`) as 'validated'. This is typically used after human-in-the-loop verification has confirmed the accuracy of AI-driven processing.

-   `POST /api/processing_tasks/{task_id}/abort`
    -   **Purpose**: Marks a specific task (identified by `task_id`) as 'aborted', indicating it should not proceed further in the workflow, often due to errors or a decision made during validation.

---

**General Note**: All API endpoints are designed to return responses in JSON format. For the most detailed and up-to-date information on API endpoint behavior, request/response schemas, and specific implementation details, please refer to the backend source code, particularly in `backend/backend_main.py` and related routing or controller files.
