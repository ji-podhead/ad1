# Identified Issues and Status

## 1. Backend: `socket.gaierror: [Errno -2] Name or service not known`

*   **Description:** The backend service fails to start due to a `socket.gaierror` when trying to connect to the PostgreSQL database. This occurs because the `DATABASE_URL` in `docker-compose.yml` specifies `db` as the hostname, but due to `network_mode: host`, the service should connect via `localhost`.
*   **Status:** Fixed. The `DATABASE_URL` in `docker-compose.yml` has been changed from `postgresql://postgres:postgres@db:5432/mailwhisperer` to `postgresql://postgres:postgres@localhost:5432/mailwhisperer`.

## 2. Frontend: `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`

*   **Description:** The frontend fails to parse the response from `/api/oauth-config` as JSON because it receives an HTML page instead. This is due to an incorrect file path construction in `backend/backend_main.py` for the `gcp-oauth.keys.json` file, leading to a 404 or server error that returns HTML.
*   **Status:** Fixed. The path in `backend_main.py`'s `get_oauth_config` function has been corrected from `os.path.join(os.path.dirname(__file__), '../auth/gcp-oauth.keys.json')` to `os.path.join(os.path.dirname(__file__), 'auth/gcp-oauth.keys.json')`.
