# ad1 Frontend

This is the frontend for the ad1 project: Automated Email & Document Processing.

## Overview

The ad1 frontend is a modern, modular React/Vite application designed for secure, compliant, and efficient document workflows. It implements all user-facing requirements from the client briefing and main project README, including:

- Email inbox and workflow triggers
- Document upload and management
- Human-in-the-loop validation
- Audit trail review
- Agent chat and task management

All user actions are reflected in the UI and sent to the backend for audit logging and processing. The UI is designed for compliance and usability, with clear status indicators and audit trails.

## Main Pages/Views

- **Inbox** (`src/pages/Inbox.tsx`):
  - List, filter, and label emails
  - Trigger workflows on incoming emails
  - See processing status

- **Documents** (`src/pages/Documents.tsx`):
  - Upload, view, and manage documents
  - See processing status and link to validation

- **Validation** (`src/pages/Validation.tsx`):
  - Human-in-the-loop validation interface
  - Left: original document; Right: processed result (fields, handwriting, etc.)
  - Below: Approve, abort, or restart with prompt
  - Audit trail for each task is visible
  - On validation, document is encrypted and sent

- **Audit Trail** (`src/pages/Audit.tsx`):
  - View all actions and changes for compliance

- **Agent Chat** (`src/pages/AgentChat.tsx`):
  - WebSocket chat to trigger workflows, ask for status, or interact with Catbot

- **Task Section** (`src/pages/Tasks.tsx`):
  - Overview of all processing tasks, their status, and actions (select, validate, abort, etc.)

- **Layout** (`src/components/Layout.tsx`):
  - Provides consistent page structure and can be extended with navigation/sidebar

## Tech Stack

- **React** (with Vite)
- **TypeScript**
- **Tailwind CSS** (see `components.json` for config)
- **WebSocket** for agent chat
- **REST API** for backend integration

## Folder Structure

- `src/`
  - `pages/` – Main app pages (Inbox, Documents, Validation, Audit, Tasks, AgentChat)
  - `components/` – Reusable UI components (e.g., Layout)
  - `lib/` – Utility functions (recommended for API, helpers)
  - `hooks/` – Custom React hooks (recommended for API, state)
  - `index.tsx` – App entry point (routing)
  - `index.css` – Tailwind and global styles

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```

## Integration & Compliance

- The frontend expects the backend API to be running as described in the main project README.
- All data and actions are handled securely and in compliance with Swiss DSGVO, GDPR, and AI law.
- All servers and data are hosted in Switzerland (Google Cloud CH, on-prem, or Swiss providers).
- Role-based access and audit trails are enforced throughout the UI.

## Notes

- Extend the UI with additional components, hooks, and pages as needed.
- The UI is modular and can be themed or branded as required.
- For more details, see the main project README and `briefing multiagent.md`.

---
