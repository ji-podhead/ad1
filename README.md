# ad1
 ad1 is a secure, modular platform for automated email and document processing, designed to meet strict Swiss and EU compliance requirements. 
# ad1 – Automated Email & Document Processing

## Overview

ad1 is a secure, modular platform for automated email and document processing, designed to meet strict Swiss and EU compliance requirements. The system leverages intelligent agents, a persistent PostgreSQL database, audit trails, and a WebSocket-based chat for workflow orchestration. All components are hosted in Switzerland or on Swiss-compliant infrastructure, supporting both on-prem and cloud GPU options.

## Screenshots

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/742aa0c9-3ee4-40a5-827f-b9da743346fa" style="max-width:300px;"><br>
      <small>required oauth login</small>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/7fdbb396-15a8-4459-862a-e3b3939f7b7c" style="max-width:300px;"><br>
      <small>landing page after login</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/325503a6-cb18-44ab-b655-572227c702dd" style="max-width:300px;"><br>
      <small>inbox page</small>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/ed053302-7a33-4646-9c99-065d8d208375" style="max-width:300px;"><br>
      <small>documents page</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/b760c693-f9ce-4741-8c79-ee7aa41a2fba" style="max-width:300px;"><br>
      <small>tasks page</small>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/2f890d59-6e13-45b6-9d87-7a971c6dcd28" style="max-width:300px;"><br>
      <small>iam page</small>
    </td>
  </tr>
</table>

## Client Requirements (from briefing multiagent.md)

- **Swiss Hosting & Compliance**: All components (including LLMs) are hosted in Switzerland or with providers guaranteeing data residency in CH. GDPR, Swiss DSGVO, and AI law compliance are enforced. Role-based access, audit trails, and data retention policies are implemented.
- **Open-Source LLMs**: Only open-source LLMs are used, either self-hosted or via Swiss providers (e.g., SwissGPT, Infomaniak, Kvant). Optionally, a fully self-hosted LLM stack (e.g., LLaMA, Mistral) can be deployed.
- **Orchestration**: Workflows are orchestrated by a daemon and can be triggered via chat (Catbot) or automatically on new email arrival. n8n is referenced for orchestration, but the system is modular and can integrate with other orchestrators if needed.
- **Agent Layer**: Agents handle context tracking, compliance checking, document/report generation, and validation. After each processing step, human-in-the-loop validation is enforced.
- **Input/Output**: Supports ingestion of emails, PDFs, Word, and Excel files. Output includes processed documents, validation status, and audit logs. Finalized documents are encrypted and sent via email.
- **Scalability**: The architecture is modular and decoupled, allowing for easy extension with new templates, data sources, or AI models.

## Technical Architecture

- **Email Processing Daemon**: A background service integrated into the backend that periodically checks for new emails via the configured email integration (MCP server).
  - New emails are stored in the `emails` table (which now includes a `received_at` timestamp).
  - For each new email, a corresponding entry is created in the `tasks` table with an initial status (e.g., 'pending'), linking the email to a processing workflow.
- **Task & Document Workflow**: All documents and emails to be processed are tracked as tasks. Each task has a status (e.g., pending, processing, needs validation, validated, aborted, failed) and links to the original email/document.
- **Database Structure Highlights**:
    - `emails` table: Stores email content. Includes a `received_at` column to timestamp when the email was fetched.
    - `tasks` table: Tracks the state of each email processing job. Key columns include `id` (PK), `email_id` (FK to `emails`), `status`, `created_at`, and `updated_at` (automatically updated on modification).
    - `scheduler_tasks` table: Persists configurations for scheduled jobs, such as the polling interval for the email daemon.
    - `audit_trail` table: Logs all significant actions.
- **Human-in-the-Loop Validation**: After agent processing, tasks typically require manual validation. The validation UI displays the original document (left) and the processed result (right, including extracted values and handwriting recognition). Below are buttons to abort, restart (with prompt), or validate the task.
- **Audit Trail**: Every action (email ingestion, task creation, status changes, processing, validation, abort, etc.) is logged for compliance and traceability. Audit logs are visible in the UI.
- **Encryption & Secure Email Sending**: Once validated, documents are encrypted and sent via email. All transmission and storage is secured.
- **Extensible Model Integration**: For handwriting and advanced document recognition, a dedicated model is used (self-hosted or via a Swiss provider). The system is modular for future model or provider swaps.

## Workflow

1. **Email Ingestion**: Daemon fetches and classifies new emails, creating tasks for relevant documents.
2. **Document Processing**: Documents are processed by agents (including handwriting/field extraction).
3. **Validation**: Human validates the processed result in the Validation UI (original left, processed right, action buttons below).
4. **Audit Logging**: All actions are logged and visible in the Audit Trail UI.
5. **Encryption & Sending**: On validation, the document is encrypted and sent via email.
6. **Status Tracking**: Task status is updated throughout; users can see and manage all tasks.

## API Overview

- `/api/emails` – List, detail, and label emails
- `/api/documents` – Upload, list, and process documents
- `/api/validation` – Manage validation tasks (approve, abort, restart)
- `/api/audit` – View audit logs
- `/ws/agent` – WebSocket chat for agent interaction
- `GET /api/processing_tasks` – Returns a list of email processing tasks with their status and associated email details.
- `POST /api/processing_tasks/{task_id}/validate` – Marks a specific processing task as validated.
- `POST /api/processing_tasks/{task_id}/abort` – Marks a specific processing task as aborted.

## Frontend Structure

- **Inbox**: List and filter all emails, see processing status, trigger workflows, and label emails.
- **Documents**: Upload, view, and manage documents. See processing status and link to validation.
- **Validation**: Human-in-the-loop validation interface. Left: original document; Right: processed result (fields, handwriting, etc.). Below: Approve, abort, or restart with prompt. Audit trail for each task is visible. On validation, document is encrypted and sent.
- **Audit Trail**: View all actions and changes for compliance.
- **Agent Chat**: WebSocket chat to trigger workflows, ask for status, or interact with Catbot.
- **Task Section**: Displays email processing tasks fetched from the backend (`/api/processing_tasks`). Shows current status (e.g., 'pending', 'validated', 'aborted'), associated email details (subject, sender, received date), and task timestamps (last updated). Allows users to perform actions like "Validate" or "Abort" on these tasks, which calls the respective backend APIs.

## Security & Compliance

- All data and servers are hosted in Switzerland (Google Cloud CH, on-prem, or Swiss providers)
- Encryption for data at rest and in transit
- GDPR, Swiss DSGVO, and AI law compliance
- Role-based access and audit trails

## Quick Start

1. **Requirements**: Docker, Docker Compose
2. **Start the system**:
   ```bash
   docker compose up --build
   ```
3. **Frontend**: Start with `npm run dev` in the `frontend/` directory (if developing locally)
4. **Database**: Initialized automatically

## File Structure

- `backend/` – FastAPI backend (agents, email, document, validation, audit)
- `frontend/` – React/Vite frontend (Inbox, Documents, Validation, Audit, Chat, Tasks)
- `db/` – Database initialization scripts
- `mcp/` – MCP server for email integration

## System Architecture (Mermaid Diagram)

![image](https://github.com/user-attachments/assets/69a59c73-d3b7-44bd-af34-f6b094eb7a22)

## User & Admin Management (IPAM)

- The IPAM page allows administrators to create new users (Google Mail only), assign roles (read, write, validate, download), and toggle admin status.
- All user data is stored in the database (`users` table).
- The initial admin user is set via environment variables in `docker-compose.yml` (`INIT_ADMIN_EMAIL`, `INIT_ADMIN_PASSWORD`).
- User management is fully integrated with the backend API (`/api/users`).

## Deployment

You can deploy ad1 on-premises or in the cloud. Example scenarios:

### Tailscale On-Premises (Local)

1. Install [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) on your server or VM.
2. (Optional) Set up [Tailscale](https://tailscale.com/) for secure private networking between your devices and the deployment server.
3. Clone the repository and configure environment variables as needed (see `docker-compose.yml`).
4. Start the stack:
   ```bash
   docker compose up --build
   ```
5. Access the frontend via the server's local/private IP (e.g., `http://<your-server-ip>:3000`).

### Google Cloud (GCP)

1. Create a VM or use Google Cloud Run for containerized deployment.
2. Ensure required ports are open (frontend, backend, database).
3. Set environment variables for production (see `docker-compose.yml`).
4. Deploy using Docker Compose or build/push images to Google Artifact Registry and deploy via GCP tools.
5. (Optional) Use Google Secret Manager for sensitive config.

For both scenarios, ensure compliance with Swiss/EU data residency and security requirements. For more details, see the documentation and `briefing multiagent.md`.

## Google OAuth Setup (Frontend & Backend)

To use Google Login and Gmail API, you must create OAuth credentials and a project in Google Cloud. Follow these steps to ensure correct setup for both frontend and backend:

### 1. Enable Gmail API
- Go to the [Google Cloud Console](https://console.cloud.google.com/)
- Create a new project or select your existing project
- Navigate to **APIs & Services > Library**
- Search for **Gmail API** and click **Enable**

### 2. Create OAuth 2.0 Credentials
- Go to **APIs & Services > Credentials**
- Click **Create Credentials > OAuth client ID**
- Choose **Web application**
- Set a name (e.g. `ad1-frontend`)
- **Under Authorized redirect URIs add (for local dev and production as needed):**
  - `http://localhost:3000/oauth2callback`
  - `http://localhost:5173/oauth2callback`
  - `http://localhost:5173`
  - (add your production URI if needed)
- **Under Authorized JavaScript origins add:**
  - `http://localhost:3000`
  - `http://localhost:5173`
  - (add your production origin if needed)
- Click **Create**
- Download the `gcp-oauth.keys.json` file and place it in `auth/gcp-oauth.keys.json` and `backend/auth/gcp-oauth.keys.json`

### 3. Set OAuth Scopes
- Required scopes for Gmail API:
  - `openid`
  - `email`
  - `profile`
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/gmail.send`
- Set these in the OAuth consent screen and in your code when requesting tokens.

### 4. Docker Compose Setup
- The `docker-compose.yml` mounts the `gcp-oauth.keys.json` into the backend container automatically.
- No need to set the client ID in `.env` anymore.

### 5. Troubleshooting
- If you see errors like `redirect_uri_mismatch` or `The given origin is not allowed for the given client ID`, double-check that **both** the redirect URIs and JavaScript origins are correctly set in the Google Cloud Console **and** in your `gcp-oauth.keys.json` file.
- The frontend (Vite) often runs on port 5173 by default. Make sure this port is included in both lists.
- For production, add your deployed domain(s) to both lists as well.

---

## Infrastructure as Code (IaC) & Deployment

This repository includes ready-to-use Terraform modules for Google Cloud:

- `iac/google/gmailApi/`: Automates Gmail API activation and OAuth client creation (see `main.tf` and `example.tf`).
- `iac/google/app/`: Deploys the ad1 frontend (public) and backend (private) as Cloud Run services. Optional GKE (Kubernetes) example included.

**How to use:**
1. Install [Terraform](https://www.terraform.io/downloads.html)
2. Adjust the variables in the respective `main.tf`/`example.tf` (e.g. `project_id`, `support_email`, Images etc.)
3. Run `terraform init && terraform apply` in the respective folder

---

## MCP Server & SSE Transport

ad1 uses its own MCP (Mail Control Protocol) Server for secure email integration. The communication between frontend and MCP occurs over Server-Sent Events (SSE):

- **MCP Server:** Runs as its own container/service (see `docker-compose.yml` and `mcp/` folder)
- **SSE Transport:** The frontend connects to the MCP server via an SSE URL (e.g. `MCP_SERVER_URL=http://localhost:8000/mcp-server/sse/`)
- **Benefits:** Real-time updates, no polling load, robust for compliance and audit trails
- **Configuration:** The MCP URL is set via an environment variable and used in the frontend/backend

For more details on MCP integration and SSE endpoints, refer to the backend documentation and the `mcp/` folder.

---

## Backend API

The ad1 backend exposes a secure REST API for all core functions. All endpoints require authentication via Google OAuth. The backend determines user roles (admin, user) based on the email address after login.

### Main Endpoints

- **/api/oauth-config** (GET):
  - Returns the Google OAuth client configuration (client_id etc.) for the frontend.
  - Used by the frontend to initialize Google Login.

- **/api/userinfo** (POST):
  - Request body: `{ "email": "user@gmail.com", "token": "<optional>" }`
  - Returns: `{ "is_admin": true/false, "roles": [ ... ] }`
  - Used by the frontend after Google login to determine user roles and admin status.

- **/api/emails** (GET):
  - List all emails in the system.

- **/api/emails/{email_id}** (GET):
  - Get details for a specific email.

- **/api/emails/{email_id}/label** (POST):
  - Set or update the label for an email.

- **/api/audit** (GET):
  - Retrieve the audit trail for compliance and traceability.

- **/api/users** (GET/POST):
  - List all users or create a new user (admin only).

- **/ws/agent** (WebSocket):
  - Real-time chat and workflow orchestration with the agent layer.

- **/api/scheduler/tasks** (GET):
  - List all scheduled tasks (document/email processing, etc.).

- **/api/scheduler/task** (POST):
  - Create a new scheduled task.

- **/api/scheduler/task/{task_id}/pause** (POST):
  - Pause or resume a scheduled task.

- **/api/scheduler/task/{task_id}** (DELETE):
  - Delete a scheduled task.
- `GET /api/processing_tasks`:
  - Retrieves a list of all email processing tasks, including their current status and details from the linked email (subject, sender, received date).
- `POST /api/processing_tasks/{task_id}/validate`:
  - Marks a specific task (identified by `task_id`) as 'validated'. This is typically used after human-in-the-loop verification.
- `POST /api/processing_tasks/{task_id}/abort`:
  - Marks a specific task as 'aborted', indicating it should not proceed further.

All endpoints return JSON. For more details, see the backend source code in `backend/backend_main.py`.

---

## Original Mockup
### Tasks
![s2](https://github.com/user-attachments/assets/11df8006-6d92-486f-b0fd-603276fb254d)
### Validation
![s1](https://github.com/user-attachments/assets/6e5424b6-2d37-49d1-9374-5c56f79cc6a6)



## License & Commercial Use

**All rights reserved.**

Any commercial use, resale, or distribution of this software (including SaaS, on-prem, or as part of another product) is strictly prohibited without a written contract with the copyright holder.

Contact the author for licensing options. All rights remain with the project owner.
