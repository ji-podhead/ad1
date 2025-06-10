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
CREDENTIALS_PATH = './auth/gmail_credentials.pickle'


def generate_auth_url():
    """
    Generates the Google OAuth 2.0 authorization URL for Gmail API access.

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
    flow = Flow.from_client_secrets_file(
        './auth/gcp-oauth.keys.json',
        scopes=['https://mail.google.com/'],
        redirect_uri='http://localhost:8001/oauth2callback')  # Updated redirect_uri

    auth_url, state = flow.authorization_url(prompt='consent')

    logger.info('Please go to this URL: {}'.format(auth_url))
    # In a real web app, you would store the state and associate it with the user's session
    # and return the auth_url to the frontend.
    return auth_url, state


def handle_oauth_callback(code, state=None):
    """
    Handles the OAuth callback, exchanges the code for tokens, and stores credentials.
    """
    # In a real web app, you would verify the state parameter here for security
    # against CSRF attacks.

    flow = Flow.from_client_secrets_file(
        './auth/gcp-oauth.keys.json',
        scopes=['https://mail.google.com/'],
        redirect_uri='http://localhost:8001/oauth2callback')  # Updated redirect_uri

    try:
        flow.fetch_token(code=code)

        # Store the credentials for future use
        credentials = flow.credentials
        with open(CREDENTIALS_PATH, 'wb') as token:
            pickle.dump(credentials, token)

        logger.info("Successfully obtained and stored Gmail credentials.")
        return True
    except Exception as e:
        logger.error(f"Error fetching token: {e}")
        return False


def get_authenticated_service():
    """
    Loads stored OAuth credentials and attempts to refresh them if expired.

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