# System Architecture

## 1. Overall System Architecture

ad1 is designed as a modular, secure, and scalable platform for automated email and document processing. It comprises a backend API built with FastAPI, a reactive frontend using React/Vite, a persistent PostgreSQL database for data storage, and several specialized services for functions like email integration (MCP Server) and workflow orchestration. The architecture emphasizes compliance with Swiss and EU regulations, featuring robust audit trails, human-in-the-loop validation, and secure data handling practices. Components are designed to be containerized using Docker for consistent deployment across various environments, including on-premise and cloud setups.

## 2. Technical Architecture Details

The core technical architecture of ad1 is built around several key components and processes:

-   **Email Processing Daemon**: A background service integrated into the backend that periodically checks for new emails via the configured email integration (MCP server).
    -   New emails are stored in the `emails` table (which includes a `received_at` timestamp).
    -   For each new email, a corresponding entry is created in the `tasks` table with an initial status (e.g., 'pending'), linking the email to a processing workflow.
-   **Task & Document Workflow**: All documents and emails to be processed are tracked as tasks. Each task has a status (e.g., pending, processing, needs validation, validated, aborted, failed) and links to the original email/document.
-   **Database Structure Highlights**:
    -   **Database Table Overview**: For a detailed description of all database tables, refer to [README_db_tables.md](README_db_tables.md).
    -   `emails` table: Stores email content. Includes a `received_at` column to timestamp when the email was fetched.
    -   `tasks` table: Tracks the state of each email processing job. Key columns include `id` (PK), `email_id` (FK to `emails`), `status`, `created_at`, and `updated_at` (automatically updated on modification).
    -   `scheduler_tasks` table: Persists configurations for scheduled jobs, such as the polling interval for the email daemon and workflow definitions.
    -   `audit_trail` table: Logs all significant actions within the system.
-   **Human-in-the-Loop Validation**: After automated agent processing, tasks typically require manual validation by a human operator. The validation UI is designed to support this by displaying the original document alongside the processed result (including extracted values, recognized handwriting, etc.). Operators can then abort the task, restart it (potentially with modified parameters or prompts), or validate and approve the task.
-   **Audit Trail**: Every significant action within the system is logged to ensure compliance and traceability. This includes events like email ingestion, task creation, status changes, processing steps, validation decisions (approve, abort), and any errors encountered. Audit logs are accessible through the UI.
-   **Encryption & Secure Email Sending**: Once documents are validated and finalized, they are encrypted before being sent via email. All data transmission and storage within the system are secured using appropriate encryption mechanisms.
-   **Extensible Model Integration**: For functionalities like handwriting recognition and advanced document analysis, ad1 integrates with specialized AI models. These models can be self-hosted or accessed via Swiss-compliant third-party providers. The system is designed to be modular, allowing for future updates or swaps of AI models or providers as requirements evolve.

## 3. System Architecture Diagram

The following diagram illustrates the high-level architecture of the ad1 system, showing the main components and their interactions.

![image](https://github.com/user-attachments/assets/69a59c73-d3b7-44bd-af34-f6b094eb7a22)

This diagram depicts the flow of information from email ingestion through processing, validation, and final output, highlighting the roles of the backend, frontend, database, and MCP server.

## 4. Core Workflow

The typical workflow for processing an email or document in ad1 involves the following stages:

1.  **Email Ingestion**: The Email Processing Daemon fetches new emails from the configured mail source (via MCP Server). Emails are classified, and relevant documents are identified, leading to the creation of new tasks.
2.  **Document Processing**: Attached documents or email content are processed by a series of AI agents. This can include steps like data extraction, handwriting recognition, field mapping, and compliance checks.
3.  **Validation**: After automated processing, the task is typically routed for human-in-the-loop validation. An operator reviews the original document and the AI-processed output via the Validation UI.
4.  **Audit Logging**: Throughout the entire process, all actions, decisions, and status changes are meticulously logged in the `audit_trail` table for compliance and historical tracking.
5.  **Encryption & Sending**: Upon successful validation, the processed document (or a report generated from it) is encrypted and securely sent via email to the intended recipient or stored as per workflow configuration.
6.  **Status Tracking**: The status of each task is updated in real-time within the `tasks` table. Users can monitor and manage tasks through the frontend interface.

## 5. Workflow Management System

ad1 incorporates a flexible workflow management system, allowing users to define and customize processing pipelines tailored to specific needs.

-   **Triggers**: Workflows can be initiated by:
    -   **Email Receive**: Automatically triggered when a new email arrives that matches certain criteria.
    -   **Cron Job**: Triggered on a predefined schedule (e.g., daily, hourly) for batch processing or routine tasks.
-   **Configuration (Summary Step)**: During the setup of a workflow (via the 'Workflow Builder' page in the frontend), users define key parameters. This includes selecting the AI model to be used (e.g., 'gpt-4', 'mistral'), setting maximum token limits for LLM interactions, and defining other operational parameters. This configuration collectively defines a 'workflow type'.
-   **Workflow Steps**: Users can then assemble a sequence of processing steps to form the workflow. Examples of available steps include:
    -   Compliance Agent (for regulatory checks)
    -   Human Verification (routes to the validation UI)
    -   Document Processing (specific data extraction or transformation)
    -   Send Email (for dispatching results)
-   **Type Assignment**: The 'workflow type' (derived from the summary configuration) is assigned to:
    -   **Tasks**: New tasks created as part of this workflow will carry this type, making it visible and filterable on the 'Tasks' page.
    -   **Documents/Emails**: Emails processed or documents generated by these workflows will also be tagged with this type, allowing for better organization and traceability on the 'Documents' page.

This system enables tailored automation flows and improves the categorization and management of processed items.

## 6. MCP Server & SSE Transport

ad1 utilizes its own MCP (Mail Control Protocol) Server for secure and efficient email integration. Communication, particularly between the frontend and the MCP server for real-time updates, occurs over Server-Sent Events (SSE).

-   **MCP Server Role**: The MCP Server acts as a dedicated gateway for handling incoming and outgoing emails. It runs as a separate containerized service (defined in `docker-compose.yml` and located in the `mcp/` directory). It manages connections to mail servers and processes email-related requests from the backend.
-   **SSE Transport**: The frontend connects to the MCP server via an SSE URL (e.g., `MCP_SERVER_URL=http://localhost:8000/mcp-server/sse/`). This allows the MCP server to push real-time updates to the frontend, such as notifications of new emails or status changes, without the need for traditional polling. This approach is robust, reduces server load, and is well-suited for applications requiring immediate feedback and audit trails.
-   **Configuration**: The URL for the MCP server is configured via environment variables, which are then used by both the frontend and backend services to establish communication.

## 7. Frontend Structure (Architectural Aspects)

The frontend of ad1, built with React/Vite, provides the user interface for all interactions with the system. Architecturally, it is a client-side application that communicates with the backend via REST APIs and WebSockets.

-   **Inbox**: Displays emails fetched by the backend, allows users to see processing status, and trigger manual workflows. Interacts with `/api/emails` and potentially task-related endpoints.
-   **Documents**: Allows users to upload, view, and manage documents. Shows processing status and links to validation. Interacts with `/api/documents` and task-related endpoints.
-   **Validation**: The human-in-the-loop interface. It fetches task details (original document and processed data) from the backend and submits validation decisions (approve, abort, restart) via API calls (e.g., `/api/processing_tasks/{task_id}/validate`).
-   **Audit Trail**: Displays logs fetched from `/api/audit`, providing a view into system activities.
-   **Agent Chat**: Utilizes a WebSocket connection (`/ws/agent`) to the backend for real-time interaction with AI agents, allowing users to trigger workflows or ask for status updates.
-   **Tasks Section**: Lists email processing tasks from `/api/processing_tasks`, showing their status and allowing users to perform actions like "Validate" or "Abort".
-   **Workflow Builder**: A dedicated page for creating and configuring custom workflows. User configurations are saved to the backend via API calls (e.g., `/api/scheduler/task`), which then manages these workflows.

The frontend is responsible for rendering data, capturing user input, and making appropriate API calls to the backend, which orchestrates the core logic and data persistence.

## 8. Global Email Processing & Workflow Execution (Future Vision for post-2025)

The planned evolution of email processing aims for a more centralized and intelligent approach:

-   **Single Global Cronjob**: Instead of multiple schedulers or per-workflow cron jobs, a single global cronjob will run regularly (interval configurable in system settings) to check for new emails.
-   **LLM Summary and Topic Determination**: For each new email, an LLM will automatically generate a summary and determine its primary topic (e.g., "Invoice", "Support Request", "Contract Review").
-   **Dynamic Workflow Execution**: The system will then iterate through all active workflows (defined as `scheduler_tasks` with status 'active' and trigger type 'cron' or 'email_receive' that matches the topic). If the `selected_topic` in a workflow's configuration matches the recognized topic of the email, that workflow will be triggered.
-   **Task Creation and Step Execution**: For each matching workflow, a new task will be created, and the sequence of steps defined within that workflow (e.g., Compliance Agent, Document Processing, Human Verification) will be executed.
-   **Centralized Configuration**: The mapping of key features and topics will be managed globally in the system settings, while the selection of a specific topic for a workflow will be part of the individual workflow's configuration. The frequency of the global cronjob will also be a central setting.

**Advantages of this approach:**
-   **Efficiency**: Only one central email check process, reducing redundancy and potential for overlapping cronjobs.
-   **Flexibility**: Workflows can be dynamically triggered based on email content (topic) and configured key features.
-   **Scalability**: Simplifies the management of numerous workflows as the system grows.
-   **Clarity**: Provides a clear, traceable processing path and enhances the audit trail.
