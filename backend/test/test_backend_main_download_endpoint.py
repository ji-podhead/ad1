import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import base64

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend_main import app # Assuming your FastAPI app instance is named 'app'
from tools_wrapper import download_attachment as actual_download_attachment # To avoid name collision

# Test data
DUMMY_ATTACHMENT_BYTES = b"dummy attachment content"
MOCK_FILENAME = "test_attachment.pdf"
MOCK_CONTENT_TYPE = "application/pdf"
MOCK_GOOGLE_MSG_ID = "google_msg_123"
MOCK_GOOGLE_ATT_ID = "google_att_abc"

# Create a TestClient instance
client = TestClient(app)

# --- Mocks ---

# Mock for database pool and connection
mock_db_pool = AsyncMock()
mock_db_conn = AsyncMock()

# Mock for tools_wrapper.download_attachment
mock_tools_download_attachment = AsyncMock()

# Mock for placeholder auth
mock_user_auth_placeholder = AsyncMock()


@pytest.fixture(autouse=True)
def setup_mocks_for_tests():
    # This fixture will run before each test

    # Reset mocks to a clean state for each test
    mock_db_pool.reset_mock()
    mock_db_conn.reset_mock()
    mock_tools_download_attachment.reset_mock()
    mock_user_auth_placeholder.reset_mock()

    # Setup default behaviors
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_db_conn

    # Patch app.state.db if it's initialized at startup
    # This assumes app.state.db is set to the pool during app startup.
    # If app.state.db is directly used, patch it. If it's request.app.state.db, it's harder.
    # For TestClient, it's better to patch the functions that use the pool.
    # Let's assume the endpoint uses `request.app.state.db` which TestClient should handle if `app.state.db` is patched before app creation for tests.
    # A common pattern is to override dependencies in FastAPI for testing.
    # For now, we'll patch where the db_pool is used in the endpoint if direct patching of app.state is complex.
    # The endpoint uses `request.app.state.db` so we need to ensure `app.state.db` is our mock_db_pool when the TestClient makes a request.
    # This is usually handled by FastAPI's dependency overrides or by patching at app creation for tests.
    # A simpler way for this structure is to patch `asyncpg.create_pool` if it's called by `startup()`.
    # However, `startup()` is already run by TestClient.
    # The most direct way here is to ensure `app.state.db` is patched within the test client's scope if possible,
    # or patch the specific `fetchrow` etc. calls on the pool object if it's accessed globally.

    # For this structure, let's assume the placeholder auth calls db_pool.fetchrow
    # And the main endpoint logic calls db_pool.fetchrow
    # So, mock_db_conn.fetchrow will be our main target for DB results.

    # Default successful auth placeholder behavior
    mock_user_auth_placeholder.return_value = MagicMock(
        id=1,
        email="testuser@example.com",
        google_access_token="valid_mock_token"
    )
    # Default successful tools_wrapper.download_attachment behavior
    mock_tools_download_attachment.return_value = DUMMY_ATTACHMENT_BYTES

    # Apply patches
    patcher_tools_download = patch('backend_main.download_attachment', mock_tools_download_attachment)
    patcher_tools_download.start() # Start the patch

    # Forcing app.state.db to be our mock_db_pool for the duration of tests
    original_db = None
    if hasattr(app.state, 'db'): # Ensure app.state has db attribute
        original_db = app.state.db
        app.state.db = mock_db_pool
    else:
        # If app.state.db is not set up (e.g. if startup event hasn't run or is mocked out),
        # this won't take effect. Dependency injection is usually preferred for robust testing.
        # For now, we'll assume it's available or the direct patching of db calls in functions will work.
        # If direct patching isn't done, this test setup might rely on the app's actual DB setup.
        # Given the endpoint uses request.app.state.db, this should work if TestClient sets up app.state.
        # Let's add a temporary attribute if it doesn't exist to avoid errors, though this is not ideal.
        if not hasattr(app.state, 'db'):
            app.state.db = mock_db_pool # Temporarily set if not present.
            logger.warning("app.state.db was not initialized. Temporarily setting for tests. Consider dependency injection for DB.")


    yield # Test runs here

    # Teardown: Stop patches and restore original state
    patcher_tools_download.stop()
    if original_db: # Restore only if we had an original
        app.state.db = original_db
    elif hasattr(app.state, 'db') and app.state.db is mock_db_pool:
        # If we set it temporarily and there was no original, remove it or set to a sensible default like None
        del app.state.db # Or app.state.db = None


# --- Test Cases ---

def test_download_attachment_success():
    # Setup DB mock for this specific test
    mock_db_conn.fetchrow = AsyncMock(side_effect=[
        # First call for placeholder auth (user_id=1)
        {"id": 1, "email": "testuser@example.com", "google_access_token": "valid_mock_token"},
        # Second call for metadata query
        {
            "filename": MOCK_FILENAME,
            "content_type": MOCK_CONTENT_TYPE,
            "google_attachment_id": MOCK_GOOGLE_ATT_ID,
            "google_message_id": MOCK_GOOGLE_MSG_ID,
        }
    ])

    with patch('backend_main.download_attachment', mock_tools_download_attachment):
      response = client.get(f"/api/emails/1/attachments/1") # internal_email_id=1, document_db_id=1

    assert response.status_code == 200
    assert response.content == DUMMY_ATTACHMENT_BYTES
    assert response.headers["content-type"] == MOCK_CONTENT_TYPE
    assert response.headers["content-disposition"] == f'attachment; filename="{MOCK_FILENAME}"'

    mock_tools_download_attachment.assert_called_once_with(
        user_id='me',
        message_id=MOCK_GOOGLE_MSG_ID,
        attachment_id=MOCK_GOOGLE_ATT_ID,
        access_token="valid_mock_token"
    )

def test_download_attachment_db_metadata_not_found():
    mock_db_conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "email": "testuser@example.com", "google_access_token": "valid_mock_token"}, # Auth
        None # Metadata query returns None
    ])
    # No need to patch download_attachment here as it won't be reached.
    response = client.get("/api/emails/1/attachments/2") # doc_id 2 not found
    assert response.status_code == 404
    assert "Attachment or email metadata not found" in response.json()["detail"]

def test_download_attachment_db_incomplete_google_ids():
    mock_db_conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "email": "testuser@example.com", "google_access_token": "valid_mock_token"}, # Auth
        { # Metadata query returns incomplete data
            "filename": MOCK_FILENAME, "content_type": MOCK_CONTENT_TYPE,
            "google_attachment_id": None, # Missing
            "google_message_id": MOCK_GOOGLE_MSG_ID,
        }
    ])
    response = client.get("/api/emails/1/attachments/3")
    assert response.status_code == 500
    assert "Stored metadata is incomplete" in response.json()["detail"]

def test_download_attachment_auth_placeholder_user_not_found():
    mock_db_conn.fetchrow = AsyncMock(return_value=None) # Auth query fails
    response = client.get("/api/emails/1/attachments/1")
    assert response.status_code == 401
    assert "User not configured for placeholder auth" in response.json()["detail"]

def test_download_attachment_auth_placeholder_no_token():
    mock_db_conn.fetchrow = AsyncMock(return_value= {"id": 1, "email": "testuser@example.com", "google_access_token": None}) # Auth query shows no token
    response = client.get("/api/emails/1/attachments/1")
    assert response.status_code == 401
    assert "User token not available for placeholder auth" in response.json()["detail"]


def test_download_attachment_wrapper_raises_404():
    mock_db_conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "email": "testuser@example.com", "google_access_token": "valid_mock_token"},
        {"filename": MOCK_FILENAME, "content_type": MOCK_CONTENT_TYPE, "google_attachment_id": MOCK_GOOGLE_ATT_ID, "google_message_id": MOCK_GOOGLE_MSG_ID}
    ])
    # Ensure the global mock_tools_download_attachment is used by the endpoint
    mock_tools_download_attachment.side_effect = ClientResponseError(request_info=MagicMock(), history=MagicMock(), status=404, message="Not Found from Google")

    response = client.get("/api/emails/1/attachments/1")

    assert response.status_code == 404
    assert "Attachment not found by Google API" in response.json()["detail"]
    mock_tools_download_attachment.side_effect = None # Reset side effect

def test_download_attachment_wrapper_raises_401():
    mock_db_conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "email": "testuser@example.com", "google_access_token": "valid_mock_token"},
        {"filename": MOCK_FILENAME, "content_type": MOCK_CONTENT_TYPE, "google_attachment_id": MOCK_GOOGLE_ATT_ID, "google_message_id": MOCK_GOOGLE_MSG_ID}
    ])
    mock_tools_download_attachment.side_effect = ClientResponseError(request_info=MagicMock(), history=MagicMock(), status=401, message="Unauthorized by Google")

    response = client.get("/api/emails/1/attachments/1")

    assert response.status_code == 401
    assert "Google API Authorization Error" in response.json()["detail"]
    mock_tools_download_attachment.side_effect = None # Reset side effect

def test_download_attachment_wrapper_raises_value_error():
    mock_db_conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "email": "testuser@example.com", "google_access_token": "valid_mock_token"},
        {"filename": MOCK_FILENAME, "content_type": MOCK_CONTENT_TYPE, "google_attachment_id": MOCK_GOOGLE_ATT_ID, "google_message_id": MOCK_GOOGLE_MSG_ID}
    ])
    mock_tools_download_attachment.side_effect = ValueError("Test decoding error")

    response = client.get("/api/emails/1/attachments/1")

    assert response.status_code == 500
    assert "Data error: Test decoding error" in response.json()["detail"]
    mock_tools_download_attachment.side_effect = None # Reset side effect


# Add a logger to avoid NameError if logger is used in the fixture and not globally defined
import logging
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    pytest.main([__file__])
