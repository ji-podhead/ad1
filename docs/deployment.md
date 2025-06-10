# Deployment Guide

## 1. Introduction to Deployment

This document provides comprehensive instructions for deploying the ad1 platform. It covers various scenarios, from local on-premises setups to cloud deployments on Google Cloud Platform (GCP). It also details essential configuration steps, including Google OAuth setup, Infrastructure as Code (IaC) usage, Docker image building, and troubleshooting common deployment issues. Following these guidelines will help ensure a smooth and secure deployment of ad1.

## 2. Deployment Scenarios

ad1 can be deployed in various environments. Below are instructions for common setups:

### Tailscale On-Premises (Local)

This scenario is suitable for development, testing, or small-scale production use where you manage the infrastructure.

1.  **Install Docker and Docker Compose**:
    *   Ensure [Docker](https://docs.docker.com/get-docker/) is installed on your server or virtual machine.
    *   Install [Docker Compose](https://docs.docker.com/compose/install/) (often included with Docker Desktop, or as a separate plugin).
2.  **(Optional) Set up Tailscale**:
    *   For secure private networking and easy access to your deployment server from anywhere, consider setting up [Tailscale](https://tailscale.com/) on your server and local machine.
3.  **Clone the Repository**:
    *   Obtain the project source code:
        ```bash
        git clone <repository_url>
        cd <repository_directory>
        ```
4.  **Configure Environment Variables**:
    *   Review the `docker-compose.yml` file for required and optional environment variables.
    *   Create a `.env` file in the project root or directly set variables in your environment as needed (e.g., for API keys, database credentials if not using defaults, `ADMIN_EMAILS`).
5.  **Start the Stack**:
    *   Build and start all services defined in `docker-compose.yml`:
        ```bash
        docker compose up --build
        ```
    *   The `--build` flag ensures images are built before starting, which is useful on the first run or after code changes.
6.  **Accessing the Frontend**:
    *   Once the containers are running, access the frontend application via the server's local IP address or, if using Tailscale, its Tailscale IP, at the configured frontend port (e.g., `http://<your-server-ip>:3000` or `http://<your-server-ip>:5173`).

### Google Cloud (GCP)

This scenario outlines deploying ad1 on Google Cloud Platform, leveraging its managed services.

1.  **Choose a Compute Option**:
    *   **Google Compute Engine (GCE)**: Deploy on a Virtual Machine for full control.
    *   **Google Cloud Run**: Deploy as containerized services for a serverless experience (recommended for scalability and ease of management). The `iac/google/app/` Terraform module provides examples for Cloud Run.
2.  **Port Configuration**:
    *   Ensure your GCP firewall rules allow traffic on the necessary ports (e.g., 80/443 for the frontend, backend API port, database port if externally accessible).
3.  **Environment Variables for Production**:
    *   Set environment variables securely. Use GCP Secret Manager or configure environment variables directly in Cloud Run service settings or GCE instance metadata. These will include database connection strings, API keys, Google OAuth credentials (client ID/secret if not using mounted files), and other production-specific settings.
4.  **Deployment Methods**:
    *   **Docker Compose (on GCE VM)**: Similar to the on-premises setup, you can use Docker Compose on a GCE VM.
    *   **GCP Native Tools (Cloud Run/GKE)**:
        *   Build Docker images (see [Backend Docker Build & Compose Usage](#5-backend-docker-build--compose-usage)) and push them to Google Artifact Registry.
        *   Deploy these images using Cloud Run service definitions or Google Kubernetes Engine (GKE) configurations. The `iac/google/app/` Terraform module automates Cloud Run deployment.
5.  **(Optional) Google Secret Manager**:
    *   Store sensitive configuration data like API keys and database passwords in Google Secret Manager and grant appropriate access to your Cloud Run services or GCE VMs.

**Compliance Note**: For both scenarios, ensure that your deployment strategy, data storage, and operational practices comply with Swiss and EU data residency, GDPR, Swiss DSGVO, and relevant AI laws. This includes choosing appropriate GCP regions if applicable.

## 3. Google OAuth Setup (Frontend & Backend)

To enable users to log in with their Google accounts and allow the application to access Google APIs (like Gmail API), you must configure Google OAuth 2.0.

1.  **Enable Gmail API**:
    *   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    *   Select or create a Google Cloud Project.
    *   Navigate to **APIs & Services > Library**.
    *   Search for "Gmail API" and click **Enable**.
2.  **Create OAuth 2.0 Credentials**:
    *   Navigate to **APIs & Services > Credentials**.
    *   Click **+ CREATE CREDENTIALS** and select **OAuth client ID**.
    *   For **Application type**, choose **Web application**.
    *   Set a **Name** (e.g., `ad1-webapp`).
    *   Under **Authorized JavaScript origins**, add URIs for your frontend:
        *   `http://localhost:3000` (if using this port for local dev)
        *   `http://localhost:5173` (default Vite dev port)
        *   *Add your production frontend URI(s) here.*
    *   Under **Authorized redirect URIs**, add URIs where users will be redirected after authentication:
        *   `http://localhost:3000/oauth2callback`
        *   `http://localhost:5173/oauth2callback`
        *   *Add your production redirect URI(s) here.*
    *   Click **CREATE**.
3.  **Download `gcp-oauth.keys.json`**:
    *   After creating the client ID, a dialog will show your Client ID and Client secret. You can also download the credentials as a JSON file. Click **DOWNLOAD JSON**.
    *   Rename this file to `gcp-oauth.keys.json`.
    *   Place this file in `auth/gcp-oauth.keys.json` (for frontend, if needed directly) and primarily in `backend/auth/gcp-oauth.keys.json` as the backend handles the core OAuth logic. The `iac/google/gmailApi/` Terraform module can also help manage these keys.
4.  **Set OAuth Scopes**:
    *   Ensure your application requests the correct OAuth scopes. These are typically defined in your backend code where the Google API client is initialized. Required scopes for ad1 typically include:
        *   `openid`
        *   `email`
        *   `profile`
        *   `https://www.googleapis.com/auth/gmail.readonly`
        *   `https://www.googleapis.com/auth/gmail.send` (if sending emails)
    *   Configure these scopes in the OAuth consent screen settings in the Google Cloud Console.
5.  **Docker Compose Setup for `gcp-oauth.keys.json`**:
    *   The `docker-compose.yml` file should mount the `gcp-oauth.keys.json` file into the backend container (and MCP server if it directly interacts with Gmail API). Example:
        ```yaml
        services:
          backend:
            volumes:
              - ./backend/auth/gcp-oauth.keys.json:/app/auth/gcp-oauth.keys.json:ro
          # Potentially mcp server if it needs direct access
          # mcp:
          #   volumes:
          #     - ./backend/auth/gcp-oauth.keys.json:/app/auth/gcp-oauth.keys.json:ro
        ```
    *   This makes the keys available to the application inside the container. The application should be configured to read these keys from the specified path.
6.  **Troubleshooting OAuth Issues**:
    *   **`redirect_uri_mismatch`**: This error means the URI a user is being redirected to after Google login is not listed in the "Authorized redirect URIs" in your Google Cloud Console OAuth client settings. Ensure all possible URIs (dev, prod, different ports) are listed.
    *   **`Error 400: origin_not_allowed`** / **`The given origin is not allowed for the given client ID`**: The JavaScript origin from where the login request is initiated is not listed in the "Authorized JavaScript origins". Ensure your frontend\'s hosting URI is correctly added.
    *   Double-check that the client ID used in your application matches the one for which you configured these URIs.
    *   Ensure the `gcp-oauth.keys.json` file content matches the credentials in the Google Cloud Console.

## 4. Infrastructure as Code (IaC) & Deployment

This repository includes Terraform modules to automate the deployment of ad1 on Google Cloud.

-   **Modules**:
    -   `iac/google/gmailApi/`: Automates the enabling of the Gmail API and the creation of necessary OAuth 2.0 client credentials. Refer to `main.tf` and `example.tf` within this directory for usage.
    -   `iac/google/app/`: Deploys the ad1 frontend (as a public Cloud Run service) and backend (as a private Cloud Run service). It also includes examples or configurations for related resources like load balancers or databases if applicable. An optional GKE (Google Kubernetes Engine) example might also be included.
-   **How to Use**:
    1.  **Install Terraform**: Download and install [Terraform](https://www.terraform.io/downloads.html).
    2.  **Configure Variables**: Navigate to the specific module directory (e.g., `iac/google/app/`). Adjust variables in `terraform.tfvars` or directly in `main.tf`/`example.tf` files (e.g., `project_id`, `region`, `support_email`, Docker image names/tags from Artifact Registry).
    3.  **Initialize and Apply**: Run the following commands in the module directory:
        ```bash
        terraform init
        terraform apply
        ```
    4.  Review the plan and type `yes` to apply the changes.

## 5. Backend Docker Build & Compose Usage

Instructions for building the backend Docker image locally and using it with Docker Compose.

### Backend-Image lokal bauen (Building the backend image locally)

1.  **Build the Image**:
    ```bash
    docker build -f build/Dockerfile.backend -t orchestranexus/agentbox:0.0.0 .
    ```
    *   `-f build/Dockerfile.backend`: Specifies the path to the Dockerfile for the backend.
    *   `-t orchestranexus/agentbox:0.0.0`: Sets the tag (name and version) for the image. Replace with your desired image name and tag.
    *   `.`: Specifies the build context (the project root directory).
2.  **Start the Stack with the Local Image**:
    *   Ensure your `docker-compose.yml` is configured to use the image tag you specified (e.g., `image: orchestranexus/agentbox:0.0.0`) or uses the `build` context for the backend service.
    ```bash
    docker compose up --build
    ```
    *   The `--build` flag ensures that Docker Compose rebuilds the image if the Dockerfile or context has changed. If the `docker-compose.yml` for the backend service specifies a `build:` section, it will build it using that context. If it specifies an `image:` tag that matches your local build, it will use that.
3.  **Optional: Bypass Cache**:
    *   If you encounter issues with caching during the build process, you can force a rebuild without cache:
        ```bash
        docker build --no-cache -f build/Dockerfile.backend -t orchestranexus/agentbox:0.0.0 .
        ```

### Hinweise (Notes)

-   Ensure that the `Dockerfile.backend` correctly installs all necessary dependencies (e.g., via `pip install -r requirements.txt`).
-   If your `docker-compose.yml` uses a `build` section for the backend service, it will typically build and use that local image by default when you run `docker compose up --build`.
-   If you make changes to the backend code or its dependencies, you will need to rebuild the Docker image for those changes to take effect in the container.

## 6. Troubleshooting Common Issues

### Problem: OAuth/Google Login or Gmail API does not work ("No refresh token is set" or similar)

Occasionally, especially after a fresh setup, when OAuth credentials change, or when running containers on a new machine for the first time, you might encounter errors related to Google OAuth or Gmail API access, such as:

```
gmail-1 | Please visit this URL to authenticate: https://accounts.google.com/o/oauth2/v2/auth?...&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Foauth2callback
mw-backend | INFO:agent_scheduler:Raw MCP tool response: 'Error: No refresh token is set.'
```
This often indicates that the application (specifically the component interacting with Gmail, like the MCP server or a dedicated Gmail service) hasn't obtained a refresh token from Google.

#### Solution: Manual OAuth Authentication Flow

This process typically applies to services that need to maintain persistent access to Gmail (like the MCP server if it's fetching emails).

1.  **Start the Containers**:
    *   Run your usual command to start the application stack:
        ```bash
        sudo docker compose up --build
        ```
        (Use `sudo` if your Docker setup requires it).
2.  **Watch Container Logs**:
    *   Monitor the logs of the container responsible for Gmail integration (e.g., `gmail`, `mcp-server`, or a similar service name defined in your `docker-compose.yml`).
    *   Look for a log message prompting you to visit a URL for authentication, for example:
        ```
        gmail-1 | Please visit this URL to authenticate: https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=...&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Foauth2callback&scope=...
        ```
3.  **Authenticate in Browser**:
    *   Copy the **full URL** from the log output.
    *   Paste it into your web browser.
    *   Log in with the Google account you want the application to use for accessing Gmail.
    *   Grant the requested permissions on the Google consent screen.
    *   After successful authentication, Google will redirect you to the `redirect_uri` specified in the URL. The application (listening at that redirect URI) should capture the authorization code and exchange it for an access token and a refresh token.
4.  **Confirmation**:
    *   Check the container logs again. You should see a message indicating that authentication was completed successfully and the refresh token has been stored (e.g., in a volume, or a local file within the container that's persisted).
        ```
        gmail-1 | Authentication completed successfully. Refresh token stored.
        ```
5.  **Rebuild and Restart (If Necessary)**:
    *   In some cases, a restart might be needed for all services to pick up the newly acquired token or updated status.
        ```bash
        sudo docker compose down
        sudo docker compose up --build
        ```

#### Example Log Output During Manual Auth

```
gmail-1 | Please visit this URL to authenticate: https://accounts.google.com/o/oauth2/v2/auth?...&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Foauth2callback
gmail-1 | Authentication code received.
gmail-1 | Exchanging code for tokens...
gmail-1 | Authentication completed successfully. Refresh token stored.
```

#### Notes for Manual Auth:

-   If you still see "No refresh token is set" errors, you may need to repeat the manual authentication flow.
-   Ensure the `gcp-oauth.keys.json` file is correctly mounted into the relevant container and that its contents match the credentials in the Google Cloud Console.
-   The `redirect_uri` in the authentication URL from the logs **must** be one of the URIs registered in your Google Cloud OAuth client ID configuration. If the service requiring authentication is running headlessly (like the `gmail-1` container), it might use a simple `http://localhost...` redirect that it can listen on internally.
-   This manual step is often a one-time requirement per environment or when credentials change, as the refresh token, once obtained, allows the application to get new access tokens without further manual intervention.
