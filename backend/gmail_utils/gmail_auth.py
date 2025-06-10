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
    Generates the Gmail OAuth authorization URL.
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
    Loads stored credentials and returns an authenticated Gmail service object.
    If credentials are not found or are expired, attempts to refresh them.
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