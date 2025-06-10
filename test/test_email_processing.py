import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import datetime
import asyncpg # For type hinting and potential exceptions

# Import the FastAPI app instance
# Ensure this path is correct relative to where pytest is run from
# Typically, if tests are in `backend/test` and main app is in `backend/`,
# and pytest is run from `backend/`, then:
# from backend_main import app # This might require path adjustments or conftest.py
# For now, let's assume we can import app and then override its state for testing.
# If not, we might need to adjust sys.path or use a conftest.py for proper app loading.

# For testing agent_scheduler.check_new_emails
from agent_scheduler import check_new_emails

# Placeholder for app import, will be refined if direct import fails
# from backend_main import app # This is the ideal import

# --- Fixtures ---

@pytest.fixture
def mock_db_pool():
    """Mocks the asyncpg.Pool connection pool."""
    pool = AsyncMock(spec=asyncpg.Pool)

    # Mock acquire to return a connection mock
    conn = AsyncMock(spec=asyncpg.Connection)
    pool.acquire.return_value.__aenter__.return_value = conn # For 'async with pool.acquire() as conn:'

    # Pre-configure common methods on the connection mock
    conn.fetchval = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.execute = AsyncMock()
    conn.close = AsyncMock()
    return pool

@pytest.fixture(scope="function")
def test_app_with_mock_db(mock_db_pool):
    """
    Provides a TestClient instance with app.state.db mocked.
    This requires the 'app' to be importable and its state to be patchable.
    """
    try:
        from backend_main import app
        # This is a critical part: Replacing the actual DB pool with a mock
        # This should happen before any endpoint is hit by the TestClient
        app.state.db = mock_db_pool
        client = TestClient(app)
        yield client # provide the TestClient to the test
        # Teardown: optionally restore original db or clean up, though for mocks it's often not needed
        # For instance, if app.state.db was set by a startup event that we don't want to re-run,
        # this direct patching is simpler for unit/functional tests of endpoints.
    except ImportError:
        pytest.skip("Skipping API tests because backend_main.app could not be imported. Check PYTHONPATH or test setup.")
    except AttributeError:
        pytest.skip("Skipping API tests because app.state.db could not be patched. App structure might have changed.")


# --- Helper Data ---

def create_mock_email_data(
    msg_id="test_msg_id_1",
    subject="Test Subject",
    sender="sender@example.com",
    body="Test email body."
):
    return {
        "id": msg_id, # Assuming 'id' from list_emails is the message_id
        "subject": subject,
        "sender": sender,
        "body": body,
        # list_emails in tools_wrapper.py doesn't specify a received_date
        # check_new_emails uses datetime.datetime.now(datetime.timezone.utc)
    }

# --- Tests for check_new_emails ---

@pytest.mark.asyncio
@patch('tools_wrapper.list_emails', new_callable=AsyncMock)
async def test_check_new_emails_new_unique_email(mock_list_emails, mock_db_pool):
    """Test processing a single new, unique email."""
    mock_email = create_mock_email_data(msg_id="unique1")
    mock_list_emails.return_value = [mock_email]

    # Mock DB calls:
    # 1. Duplicate check (fetchval for existing email by subj/sender/body) -> None (not found)
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetchval.return_value = None
    # 2. Insert into emails (fetchval for RETURNING id) -> mock email_id (e.g., 1)
    # We need to make sure the same mock_db_pool is used by the function, so we pass it

    # Setup the specific mock for the insert returning id
    # This will be the second call to fetchval if we simplify check_new_emails to not use message_id from tool
    # For now, let's assume the first fetchval is for duplicate check, second is for RETURNING id.
    # The code uses subject, sender, body for duplicate check.

    # Let's refine the mock_db_pool.acquire()...fetchval sequence if needed,
    # or use side_effect if the same method is called for different purposes.
    # Current check_new_emails:
    #   fetchrow("SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3")
    #   fetchval("INSERT INTO emails ... RETURNING id")

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn_mock.fetchrow.return_value = None # No duplicate found
    conn_mock.fetchval.return_value = 1 # Mocked returned ID for the new email

    await check_new_emails(mock_db_pool)

    mock_list_emails.assert_called_once()

    # Check for duplicate
    conn_mock.fetchrow.assert_called_once_with(
        "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3",
        mock_email['subject'], mock_email['sender'], mock_email['body']
    )

    # Insert into emails table
    # The actual call inside check_new_emails is fetchval for INSERT ... RETURNING id
    # And then execute for INSERT INTO tasks

    # Call 1 to fetchval (for insert email)
    # Call 1 to execute (for insert task)
    assert conn_mock.fetchval.call_count == 1 # For the INSERT ... RETURNING id
    assert conn_mock.execute.call_count == 1 # For the INSERT INTO tasks

    # Check INSERT INTO emails (this is now a fetchval in the code)
    insert_email_call = conn_mock.fetchval.call_args_list[0]
    sql_email_insert = insert_email_call[0][0]
    args_email_insert = insert_email_call[0][1:]

    assert "INSERT INTO emails (subject, sender, body, received_at, label)" in sql_email_insert
    assert args_email_insert[0] == mock_email['subject']
    assert args_email_insert[1] == mock_email['sender']
    assert args_email_insert[2] == mock_email['body']
    assert isinstance(args_email_insert[3], datetime.datetime) # received_at
    assert args_email_insert[4] is None # label

    # Check INSERT INTO tasks
    insert_task_call = conn_mock.execute.call_args_list[0]
    sql_task_insert = insert_task_call[0][0]
    args_task_insert = insert_task_call[0][1:]

    assert "INSERT INTO tasks (email_id, status, created_at, updated_at)" in sql_task_insert
    assert args_task_insert[0] == 1 # email_id (returned from mock insert email)
    assert args_task_insert[1] == 'pending' # status
    assert isinstance(args_task_insert[2], datetime.datetime) # created_at
    assert isinstance(args_task_insert[3], datetime.datetime) # updated_at


@pytest.mark.asyncio
@patch('tools_wrapper.list_emails', new_callable=AsyncMock)
async def test_check_new_emails_duplicate_email(mock_list_emails, mock_db_pool):
    """Test processing a duplicate email."""
    mock_email = create_mock_email_data(msg_id="duplicate1")
    mock_list_emails.return_value = [mock_email]

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    # Mock DB: Duplicate check returns an existing email_id (e.g., 1)
    conn_mock.fetchrow.return_value = {'id': 1} # Simulate email found

    await check_new_emails(mock_db_pool)

    mock_list_emails.assert_called_once()
    conn_mock.fetchrow.assert_called_once_with(
        "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3",
        mock_email['subject'], mock_email['sender'], mock_email['body']
    )

    # No insertions should happen for a duplicate
    conn_mock.fetchval.assert_not_called() # No insert into emails
    conn_mock.execute.assert_not_called() # No insert into tasks


@pytest.mark.asyncio
@patch('tools_wrapper.list_emails', new_callable=AsyncMock)
async def test_check_new_emails_multiple_emails_mixed(mock_list_emails, mock_db_pool):
    """Test with a mix of new and duplicate emails."""
    email1_new = create_mock_email_data(msg_id="new_mix1", subject="New Email 1")
    email2_dup = create_mock_email_data(msg_id="dup_mix2", subject="Duplicate Email 2")
    email3_new = create_mock_email_data(msg_id="new_mix3", subject="New Email 3")
    mock_list_emails.return_value = [email1_new, email2_dup, email3_new]

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Side effect for fetchrow (duplicate check)
    # 1st call (email1_new): None (not a duplicate)
    # 2nd call (email2_dup): {'id': 20} (is a duplicate)
    # 3rd call (email3_new): None (not a duplicate)
    conn_mock.fetchrow.side_effect = [None, {'id': 20}, None]

    # Side effect for fetchval (INSERT into emails ... RETURNING id)
    # Called for email1_new (returns 10) and email3_new (returns 30)
    conn_mock.fetchval.side_effect = [10, 30] # Mocked returned IDs

    await check_new_emails(mock_db_pool)

    assert mock_list_emails.call_count == 1
    assert conn_mock.fetchrow.call_count == 3

    # Two emails should be inserted (email1_new, email3_new)
    assert conn_mock.fetchval.call_count == 2 # For INSERT emails
    # Two tasks should be created
    assert conn_mock.execute.call_count == 2 # For INSERT tasks

    # Detailed check for email1_new (first new email)
    assert conn_mock.fetchval.call_args_list[0][0][1] == email1_new['subject']
    assert conn_mock.execute.call_args_list[0][0][1] == 10 # task for email_id 10

    # Detailed check for email3_new (second new email)
    assert conn_mock.fetchval.call_args_list[1][0][1] == email3_new['subject']
    assert conn_mock.execute.call_args_list[1][0][1] == 30 # task for email_id 30


@pytest.mark.asyncio
@patch('tools_wrapper.list_emails', new_callable=AsyncMock)
async def test_check_new_emails_empty_list(mock_list_emails, mock_db_pool):
    """Test when list_emails returns an empty list."""
    mock_list_emails.return_value = []

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    await check_new_emails(mock_db_pool)

    mock_list_emails.assert_called_once()
    conn_mock.fetchrow.assert_not_called()
    conn_mock.fetchval.assert_not_called()
    conn_mock.execute.assert_not_called()


# --- Tests for API Endpoints ---

# GET /api/processing_tasks
def test_get_processing_tasks_success(test_app_with_mock_db, mock_db_pool):
    client = test_app_with_mock_db

    mock_task_data = [
        {
            "id": 1, "email_id": 101, "status": "pending",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
            "email_subject": "Subject 1", "email_sender": "sender1@example.com",
            "email_body": "Body 1", "email_received_at": datetime.datetime.now(datetime.timezone.utc),
            "email_label": "label1"
        },
        {
            "id": 2, "email_id": 102, "status": "validated",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
            "email_subject": "Subject 2", "email_sender": "sender2@example.com",
            "email_body": "Body 2", "email_received_at": datetime.datetime.now(datetime.timezone.utc),
            "email_label": None
        },
    ]
    # app.state.db is already the mock_db_pool thanks to the fixture
    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn_mock.fetch.return_value = mock_task_data

    response = client.get("/api/processing_tasks")

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data) == 2
    assert response_data[0]["id"] == mock_task_data[0]["id"]
    assert response_data[0]["email_subject"] == mock_task_data[0]["email_subject"]
    assert response_data[1]["status"] == mock_task_data[1]["status"]

    conn_mock.fetch.assert_called_once()
    assert "SELECT" in conn_mock.fetch.call_args[0][0]
    assert "FROM tasks t" in conn_mock.fetch.call_args[0][0]
    assert "LEFT JOIN emails e ON t.email_id = e.id" in conn_mock.fetch.call_args[0][0]
    assert "ORDER BY t.created_at DESC" in conn_mock.fetch.call_args[0][0]


def test_get_processing_tasks_empty(test_app_with_mock_db, mock_db_pool):
    client = test_app_with_mock_db
    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn_mock.fetch.return_value = [] # No tasks

    response = client.get("/api/processing_tasks")

    assert response.status_code == 200
    assert response.json() == []
    conn_mock.fetch.assert_called_once()


# POST /api/processing_tasks/{task_id}/validate
def test_validate_task_success(test_app_with_mock_db, mock_db_pool):
    client = test_app_with_mock_db
    task_id_to_validate = 789
    email_id_for_task = 10 # For audit log

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    # Mock for UPDATE tasks ...
    conn_mock.execute.return_value = "UPDATE 1" # Simulate one row updated
    # Mock for fetchrow (SELECT email_id FROM tasks...) for audit log
    conn_mock.fetchrow.return_value = {'email_id': email_id_for_task}

    response = client.post(f"/api/processing_tasks/{task_id_to_validate}/validate")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": f"Task {task_id_to_validate} marked as validated."}

    assert conn_mock.execute.call_count == 2 # Once for UPDATE task, once for INSERT audit

    # Check UPDATE call
    update_call = conn_mock.execute.call_args_list[0]
    assert "UPDATE tasks SET status = 'validated' WHERE id = $1" in update_call[0][0]
    assert update_call[0][1] == task_id_to_validate

    # Check fetchrow for email_id for audit
    conn_mock.fetchrow.assert_called_once_with("SELECT email_id FROM tasks WHERE id = $1", task_id_to_validate)

    # Check INSERT audit_trail call
    audit_call = conn_mock.execute.call_args_list[1]
    assert "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())" in audit_call[0][0]
    assert audit_call[0][1] == email_id_for_task
    assert audit_call[0][2] == f"task_validate:task_id_{task_id_to_validate}"


def test_validate_task_not_found(test_app_with_mock_db, mock_db_pool):
    client = test_app_with_mock_db
    task_id_not_found = 111

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn_mock.execute.return_value = "UPDATE 0" # Simulate no row updated

    response = client.post(f"/api/processing_tasks/{task_id_not_found}/validate")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Task with id {task_id_not_found} not found"}

    conn_mock.execute.assert_called_once_with(
        "UPDATE tasks SET status = 'validated' WHERE id = $1", task_id_not_found
    )
    conn_mock.fetchrow.assert_not_called() # Should not proceed to audit if task update failed


# POST /api/processing_tasks/{task_id}/abort
def test_abort_task_success(test_app_with_mock_db, mock_db_pool):
    client = test_app_with_mock_db
    task_id_to_abort = 456
    email_id_for_task = 20

    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn_mock.execute.return_value = "UPDATE 1"
    conn_mock.fetchrow.return_value = {'email_id': email_id_for_task}

    response = client.post(f"/api/processing_tasks/{task_id_to_abort}/abort")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": f"Task {task_id_to_abort} marked as aborted."}

    assert conn_mock.execute.call_count == 2
    # Check UPDATE call
    assert "UPDATE tasks SET status = 'aborted' WHERE id = $1" in conn_mock.execute.call_args_list[0][0][0]
    assert conn_mock.execute.call_args_list[0][0][1] == task_id_to_abort
    # Check audit call
    conn_mock.fetchrow.assert_called_once_with("SELECT email_id FROM tasks WHERE id = $1", task_id_to_abort)
    assert f"task_abort:task_id_{task_id_to_abort}" in conn_mock.execute.call_args_list[1][0][2]


def test_abort_task_not_found(test_app_with_mock_db, mock_db_pool):
    client = test_app_with_mock_db
    task_id_not_found = 222
    conn_mock = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn_mock.execute.return_value = "UPDATE 0"

    response = client.post(f"/api/processing_tasks/{task_id_not_found}/abort")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Task with id {task_id_not_found} not found"}
    conn_mock.execute.assert_called_once_with(
        "UPDATE tasks SET status = 'aborted' WHERE id = $1", task_id_not_found
    )
    conn_mock.fetchrow.assert_not_called()

# TODO: Consider adding a test for when fetchrow for audit log returns None (task exists but email_id is somehow null)
# Though current audit log function handles email_id=None.
