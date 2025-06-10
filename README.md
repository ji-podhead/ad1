# ad1 – Automated Email & Document Processing

## Overview

ad1 is a secure, modular platform for intelligent automation of email and document-centric workflows. Built with a focus on Swiss and EU compliance, ad1 leverages AI-powered agents, a robust PostgreSQL database, comprehensive audit trails, and a human-in-the-loop validation process to ensure accuracy and accountability. It supports flexible deployment options, including on-premise and cloud environments.

## Screenshots

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/742aa0c9-3ee4-40a5-827f-b9da743346fa" style="max-width:300px;"><br>
      <small>Required OAuth Login</small>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/7fdbb396-15a8-4459-862a-e3b3939f7b7c" style="max-width:300px;"><br>
      <small>Landing Page After Login</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/325503a6-cb18-44ab-b655-572227c702dd" style="max-width:300px;"><br>
      <small>Inbox Page</small>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/ed053302-7a33-4646-9c99-065d8d208375" style="max-width:300px;"><br>
      <small>Documents Page</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/b760c693-f9ce-4741-8c79-ee7aa41a2fba" style="max-width:300px;"><br>
      <small>Tasks Page</small>
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/2f890d59-6e13-45b6-9d87-7a971c6dcd28" style="max-width:300px;"><br>
      <small>IAM Page</small>
    </td>
  </tr>
</table>

## Project Structure

The project is organized into the following main directories:

-   `backend/`: Contains the FastAPI application, which houses the core business logic, AI agents, API endpoints, and websocket services.
-   `frontend/`: Includes the React/Vite user interface, providing the user-facing components for interacting with the system.
-   `docs/`: Stores all project documentation, including technical specifications, guides, and diagrams.
-   `db/`: Contains database initialization scripts and schema definitions for PostgreSQL.
-   `mcp/`: Houses the MCP (Mail Control Protocol) server, responsible for email integration and real-time communication.
-   `iac/`: Includes Infrastructure as Code (IaC) modules, primarily Terraform, for deploying and managing cloud resources.
-   `build/`: Contains Docker build files (`Dockerfile`s) and configurations for containerizing the application components.

## Core Features

-   **Automated Email Processing**: Ingests, classifies, and processes emails based on predefined workflows.
-   **Intelligent Document Management**: Extracts data from various document types (PDF, Word, Excel) using AI.
-   **Workflow Orchestration**: Customizable workflows to automate complex business processes.
-   **Human-in-the-Loop Validation**: Ensures accuracy and control by incorporating manual review steps.
-   **Comprehensive Audit Trails**: Logs all system actions for compliance and traceability.
-   **Secure and Compliant**: Designed with Swiss and EU data protection regulations in mind, supporting secure hosting and data handling.

## Documentation

This section serves as a central hub for all project-related documentation.

**Existing Documents:**

-   [Database Schema](docs/README_db_tables.md): Detailed description of database tables and relationships.
-   [Original Project Briefing](docs/briefing%20multiagent.md): The initial requirements and vision for the project.
-   [MCP Tools Reference](docs/mcp_tools_reference.md): Technical details about the Mail Control Protocol tools.
-   [Why Docker?](docs/whyDocker.md): Explanation of Docker usage within the project.

**Upcoming Documents (Placeholders):**

-   [System Architecture](docs/architecture.md): Detailed overview of the system's architecture, components, and interactions. (This will include the Mermaid diagram and details on MCP Server & SSE Transport, Global Email Processing, and Workflow Execution).
-   [Deployment Guide](docs/deployment.md): Instructions for deploying ad1, including on-premise and cloud scenarios, Google OAuth setup, IaC usage, Docker build/compose details, and troubleshooting tips.
-   [API Reference](docs/api_overview.md): Comprehensive documentation for all backend API endpoints.
-   [User Management Guide](docs/user_management.md): Details on user and administrator management.
-   [Workflow Configuration](docs/workflows.md): Guide to configuring and managing automated workflows.
-   [Full API & Technical Documentation](docs/sphinx/index.html): Placeholder for future Sphinx-generated comprehensive documentation.

## Client Requirements

Key requirements include Swiss hosting and compliance (GDPR, Swiss DSGVO), use of open-source LLMs, robust orchestration, an agent layer for processing, support for various input/output formats, and a scalable, modular architecture. For full details, refer to the [Original Project Briefing](docs/briefing%20multiagent.md).

## Technical Architecture

ad1 features a modular architecture with a FastAPI backend, React frontend, PostgreSQL database, and various supporting services. For a detailed explanation of the system's components, interactions, data flows, email processing, task management, validation mechanisms, and more, please see the [System Architecture](docs/architecture.md) document. The Mermaid diagram illustrating the architecture has also been moved to this document.

## Workflow

The system processes incoming emails and documents through a series of steps including ingestion, AI-powered processing, human validation, audit logging, and secure output. Detailed workflow descriptions and diagrams can be found in the [System Architecture](docs/architecture.md) document.

## API Overview

The backend provides a comprehensive REST API for managing emails, documents, validation tasks, audit logs, users, and scheduled workflows. WebSocket support is available for real-time agent interaction. For detailed API endpoint descriptions, request/response formats, and authentication mechanisms, please refer to the [API Reference](docs/api_overview.md).

## Frontend Structure

The frontend provides interfaces for Inbox management, Document handling, Validation, Audit Trail viewing, Agent Chat, Task Management, and Workflow Building. A more detailed breakdown of frontend components and their relation to the overall architecture can be found in the [System Architecture](docs/architecture.md) document.

## Security & Compliance

ad1 is designed to meet stringent security and compliance standards:
-   Data and servers hosted in Switzerland or compliant EU locations.
-   Encryption for data at rest and in transit.
-   Adherence to GDPR, Swiss DSGVO, and relevant AI regulations.
-   Role-based access control (RBAC) and comprehensive audit trails.

## User & Admin Management (IPAM)

User authentication is handled via Google OAuth. Initial admin users are set via environment variables. Administrators can manage users (create, edit, delete, assign roles) through the UI. Further details will be available in the [User Management Guide](docs/user_management.md) and [API Reference](docs/api_overview.md).

## Workflow Management

ad1 allows users to define custom processing workflows via a dedicated UI. Workflows can be triggered by new emails or scheduled cron jobs, and involve a sequence of configurable steps (e.g., compliance checks, document processing, human verification). More details can be found in the [System Architecture](docs/architecture.md) and the upcoming [Workflow Configuration](docs/workflows.md) guide.

## Deployment

Deployment instructions for various environments (on-premise, Google Cloud), including Docker Compose usage, Google OAuth setup, Infrastructure as Code (IaC) with Terraform, and troubleshooting common issues, are consolidated in the [Deployment Guide](docs/deployment.md).

## Quick Start

1.  **Requirements**: Docker, Docker Compose
2.  **Start the system**:
    ```bash
    docker compose up --build
    ```
3.  **Frontend**: If developing locally, start the frontend in the `frontend/` directory:
    ```bash
    npm run dev
    ```
4.  **Database**: Initialized automatically by Docker Compose.
5.  **Access**: Open your browser and navigate to the appropriate frontend URL (e.g., `http://localhost:5173` or `http://localhost:3000`).

## License & Commercial Use

**All rights reserved.**

This project is the property of **ji-podhead (Leonardo J.)**. Full usage rights, including distribution, are granted to the **orchestra-nexus** GitHub organization, or **Robert Schröder**.

Any other commercial use, resale, or distribution of this software (including SaaS, on-prem, or as part of another product) is strictly prohibited without a written contract with the copyright holder.

Contact the author for licensing options. All rights remain with the project owner.
