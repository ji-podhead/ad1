"""Manages Gmail API authentication using OAuth 2.0.

This module provides functions to:
- Generate a Google OAuth 2.0 authorization URL for users to grant Gmail API permissions.
- Handle the OAuth 2.0 callback from Google, exchange the authorization code for tokens,
  and store these credentials.
- Retrieve stored credentials and refresh them if they are expired.
- Fetch stored access tokens for users from the database.

Note:
    The current implementation stores credentials in a local pickle file (`gmail_credentials.pickle`),
    which is suitable for single-user or development scenarios. For multi-user applications,
    credentials should be stored securely on a per-user basis, typically in a database.
    The `get_authenticated_service` function currently returns the credentials object;
    in a full implementation, it would return an authenticated Gmail API service client.
"""
import os
import pickle
import logging
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import asyncpg # Assuming asyncpg is used for database connection
# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to store user credentials
CREDENTIALS_PATH = './auth/gmail_credentials.pickle' # Path to store pickled credentials


def generate_auth_url() -> tuple[str, str]:
    """Generates the Google OAuth 2.0 authorization URL for Gmail API access.

    This URL is presented to the user. When the user visits this URL, they are
    prompted to grant the application permission to access their Gmail data
    as defined by the scopes.

    The `redirect_uri` specified here must exactly match one of the authorized
    redirect URIs configured in the Google Cloud Console for the OAuth client ID.

    Returns:
        tuple[str, str]: A tuple containing:
            - auth_url (str): The URL to which the user should be redirected to start
              the OAuth flow.
            - state (str): A state parameter that should be stored by the calling application
              and verified during the callback phase to prevent CSRF attacks.
    """
    # Ensure client secrets file path is correct relative to this file's location
    client_secrets_path = os.path.join(os.path.dirname(__file__), '../auth/gcp-oauth.keys.json')
    if not os.path.exists(client_secrets_path):
        logger.error(f"OAuth client secrets file not found at: {client_secrets_path}")
        # Depending on application structure, might raise an error or return specific values
        raise FileNotFoundError(f"OAuth client secrets file not found: {client_secrets_path}")

    flow = Flow.from_client_secrets_file(
        client_secrets_path, # Use absolute or correct relative path
        scopes=['https://mail.google.com/'], # Define necessary scopes
        redirect_uri='http://localhost:8001/oauth2callback')

    auth_url, state = flow.authorization_url(
        access_type='offline',  # Request offline access to get a refresh token
        prompt='consent'        # Ensure consent screen is shown, good for getting refresh token first time
    )

    logger.info(f"Generated Gmail OAuth authorization URL: {auth_url}")
    logger.info(f"OAuth state parameter generated: {state}")
    return auth_url, state


def handle_oauth_callback(code: str, state: Optional[str] = None) -> bool:
    """Handles the OAuth 2.0 callback from Google.

    Exchanges the authorization code for access and refresh tokens,
    and stores these credentials locally in a pickle file.

    Args:
        code (str): The authorization code received from Google in the callback.
        state (Optional[str], optional): The state parameter received from Google.
            In a production application, this should be verified against the state
            generated during `generate_auth_url` to prevent CSRF attacks.
            Currently, this verification is not implemented here.

    Returns:
        bool: True if tokens were successfully fetched and credentials stored,
              False otherwise.
    """
    # TODO: Implement state verification for CSRF protection in a real web app.
    # if not state or state != stored_state_from_user_session:
    #     logger.error("OAuth state mismatch. Possible CSRF attack.")
    #     return False
    logger.info(f"Handling OAuth callback with code: {code[:20]}... and state: {state}")

    client_secrets_path = os.path.join(os.path.dirname(__file__), '../auth/gcp-oauth.keys.json')
    if not os.path.exists(client_secrets_path):
        logger.error(f"OAuth client secrets file not found at: {client_secrets_path} during callback.")
        return False

    flow = Flow.from_client_secrets_file(
        client_secrets_path,
        scopes=['https://mail.google.com/'], # Ensure scopes match the initial request
        redirect_uri='http://localhost:8001/oauth2callback')

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials # google.oauth2.credentials.Credentials object

        # Ensure the directory for CREDENTIALS_PATH exists
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)

        with open(CREDENTIALS_PATH, 'wb') as token_file:
            pickle.dump(credentials, token_file)

        logger.info(f"Successfully obtained and stored Gmail credentials to {CREDENTIALS_PATH}.")
        logger.info(f"Access token expires at: {credentials.expiry}")
        if credentials.refresh_token:
            logger.info("Refresh token obtained and stored.")
        else:
            logger.warning("No refresh token was obtained. User may need to re-authenticate if access token expires and cannot be refreshed.")
        return True
    except Exception as e:
        logger.error(f"Error fetching token or storing credentials during OAuth callback: {e}", exc_info=True)
        return False


def get_authenticated_service() -> Optional[Any]: # 'Any' can be 'google.oauth2.credentials.Credentials'
    """Loads stored OAuth credentials and attempts to refresh them if expired.

    This function reads credentials from a local pickle file. If credentials exist
    and are expired but have a refresh token, it attempts to refresh them.

    Note:
        This function currently returns the `google.oauth2.credentials.Credentials`
        object directly. In a full Gmail API integration, this object would be used
        to build an authenticated Gmail API service client (e.g., using
        `googleapiclient.discovery.build`). The commented-out import and build lines
        show where this would typically happen.

    Returns:
        Optional[google.oauth2.credentials.Credentials]: The loaded (and possibly refreshed)
        credentials object if successful and valid, or None if no valid credentials
        are found or refresh fails, indicating a need for re-authentication.
    """
    credentials = None
    # Load credentials from file if they exist
    if os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, 'rb') as token:
            credentials = pickle.load(token)

    # If there are no valid credentials available, initiate the login flow.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            logger.info("Refreshing Gmail access token...")
            try:
                credentials.refresh(Request())
                # Save the refreshed credentials
                with open(CREDENTIALS_PATH, 'wb') as token:
                    pickle.dump(credentials, token)
                logger.info("Access token refreshed successfully.")
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                # If refresh fails, credentials are no longer valid, need to re-authenticate
                return None  # Indicate need for re-authentication
        else:
            logger.info("No valid Gmail credentials found. Please initiate login.")
            return None  # Indicate need for initial authentication

    # Build and return the Gmail service (requires google-api-python-client and google-auth-httplib2)
    # You would typically import and use googleapiclient.discovery here
    # from googleapiclient.discovery import build
    # service = build('gmail', 'v1', credentials=credentials)
    # return service
    logger.info("Authenticated Gmail session available.")
    # For now, just return the credentials object or a simple indicator of success
    return credentials  # Or the built service object




async def fetch_access_token_for_user(db_pool: asyncpg.pool.Pool, user_email: str) -> str:
        logger.info(f"Attempting to fetch access token for user: {user_email} for message fetch test.")
        user_row = await db_pool.fetchrow("SELECT google_access_token FROM users")
        if not user_row or not user_row['google_access_token']:
            logger.error(f"Google access token not found for user: {user_email}. Cannot perform message fetch test.")
            return None
        user_oauth_token = user_row['google_access_token']
        logger.info(f"Successfully fetched access token for user: {user_email} for message fetch test.")
        return user_oauth_token