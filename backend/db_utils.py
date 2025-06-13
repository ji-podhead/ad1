import asyncpg
import logging
import json
from typing import Optional, List, Dict, Any
import datetime
import uuid # Import uuid module

logger = logging.getLogger(__name__)

# --- Helper to get db_pool ---
async def get_db_pool(context: Any) -> asyncpg.pool.Pool:
    '''
    Helper to get db_pool from various contexts like FastAPI request, app state, or direct pool.

    :param context: The context from which to retrieve the db_pool.
                    This can be a FastAPI Request object, an App object,
                    an app.state object, or an asyncpg.pool.Pool itself.
    :type context: Any
    :raises ValueError: If the db_pool cannot be retrieved from the provided context.
    :returns: The database connection pool.
    :rtype: asyncpg.pool.Pool
    '''
    if hasattr(context, 'app') and hasattr(context.app, 'state') and hasattr(context.app.state, 'db'):
        return context.app.state.db  # FastAPI Request object
    elif hasattr(context, 'state') and hasattr(context.state, 'db'):
        return context.state.db  # FastAPI App object directly
    elif hasattr(context, 'db'): # Direct app.state object
         return context.db
    elif isinstance(context, asyncpg.pool.Pool):  # Already a pool
        return context
    raise ValueError("Could not retrieve db_pool from the provided context.")

# --- Audit Log Functions ---
async def get_audit_trail_db(db_pool: asyncpg.pool.Pool, limit: int = 50) -> List[Dict[str, Any]]:
    '''
    Retrieves the latest audit trail entries from the database.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param limit: The maximum number of audit entries to retrieve, defaults to 50.
    :type limit: int
    :returns: A list of dictionaries, where each dictionary represents an audit trail entry.
              The 'data' field (JSONB from DB) is parsed into a Python dict.
              The 'event_type' field is used directly as is from the DB.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch(
        """
        SELECT id, event_type, username, timestamp, data
        FROM audit_trail
        ORDER BY timestamp DESC
        LIMIT $1
        """,
        limit
    )
    
    processed_rows = []
    for row_proxy in rows:
        row = dict(row_proxy)
        # Parse the 'data' field from JSON string to dict if it's a string
        # asyncpg might return dict directly for JSONB depending on setup, but explicit parsing is safer.
        if row.get('data') and isinstance(row['data'], str):
            try:
                row['data'] = json.loads(row['data'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON for audit trail data: {row['data']}")
                row['data'] = {} # Default to empty dict on error
        elif row.get('data') is None: # Handle cases where data might be NULL in DB
            row['data'] = {}
        
        # event_type is now directly used by the Pydantic model, no renaming needed.
        # Ensure event_type exists, or provide a default if it can be NULL in DB
        # (though it's not defined as nullable in your db_init.sql for audit_trail)
        if 'event_type' not in row or row['event_type'] is None:
            row['event_type'] = "unknown_event" # Fallback if necessary
            
        processed_rows.append(row)
    return processed_rows

async def log_generic_action_db(
    db_pool: asyncpg.pool.Pool,
    username: str = "system_event",
    event_type: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> None:
    '''
    Logs a generic action to the audit_trail table.
    email_id, task_id, document_id are now expected to be within the 'data' dict if relevant.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param username: The username performing the action, defaults to "system_event".
    :type username: str
    :param event_type: Optional type of the event.
    :type event_type: Optional[str]
    :param data: Optional dictionary containing all relevant context about the event, including any IDs.
    :type data: Optional[Dict[str, Any]]
    :returns: None
    :rtype: None
    '''
    try:
        log_data = data if data is not None else {}
        data_json = json.dumps(log_data) if log_data else None

        await db_pool.execute(
            """
            INSERT INTO audit_trail (username, timestamp, event_type, data)
            VALUES ($1, NOW(), $2, $3)
            """,
            username, event_type, data_json
        )
        action_desc_for_log = log_data.get("action_description", "No description provided")
        logger.debug(f"Audit log: {action_desc_for_log} (Type: {event_type}) by {username}")
    except Exception as e:
        action_desc_for_error = data.get("action_description", "No description provided") if data else "No description provided"
        logger.error(f"Failed to log generic action '{action_desc_for_error}' (Type: {event_type}) by '{username}': {e}")

async def log_task_action_db(
    db_pool: asyncpg.pool.Pool,
    task_id: int,
    action: str, # This is now the action description to be put in data
    user: str = "system_user",
    data: Optional[Dict[str, Any]] = None
) -> None:
    '''
    Logs a task-specific action to the audit_trail table.
    Task ID is now part of the 'data' dictionary.
    '''
    try:
        task_details = await db_pool.fetchrow(
            "SELECT email_id, status, workflow_type FROM tasks WHERE id = $1", task_id
        )
        db_email_id_for_context = None # For potential cross-referencing if needed in data
        task_status = "N/A"
        workflow_type = "N/A"
        if task_details:
            db_email_id_for_context = task_details['email_id']
            task_status = task_details['status']
            workflow_type = task_details['workflow_type']
        
        log_data = data if data is not None else {}
        log_data.update({
            "action_description": action,
            "task_id": task_id, # Ensure task_id is in the data payload
            "email_id_context": db_email_id_for_context, # Optional: context for the task's email
            "task_status": task_status,
            "workflow_type": workflow_type
        })

        await log_generic_action_db(
            db_pool,
            username=user,
            event_type="task_event", # Generic event_type for task-related logs
            data=log_data
        )
    except Exception as e:
        logger.error(f"Failed to log task action '{action}' for task {task_id}, user '{user}': {e}")

async def log_email_action_db(
    db_pool: asyncpg.pool.Pool,
    email_id: int,
    action: str, # This is now the action description to be put in data
    user: str = "system_user",
    data: Optional[Dict[str, Any]] = None
) -> None:
    '''
    Logs an email-specific action to the audit_trail table.
    Email ID is now part of the 'data' dictionary.
    '''
    try:
        email_details = await db_pool.fetchrow(
            "SELECT subject, sender, label FROM emails WHERE id = $1", email_id
        )
        email_subject = "N/A"
        email_sender = "N/A"
        email_label = "N/A"
        if email_details:
            email_subject = email_details['subject']
            email_sender = email_details['sender']
            email_label = email_details['label']

        log_data = data if data is not None else {}
        log_data.update({
            "action_description": action,
            "email_id": email_id, # Ensure email_id is in the data payload
            "email_subject": email_subject,
            "email_sender": email_sender,
            "email_label": email_label
        })

        await log_generic_action_db(
            db_pool,
            username=user,
            event_type="email_event", # Generic event_type for email-related logs
            data=log_data
        )
    except Exception as e:
        logger.error(f"Failed to log email action '{action}' for email {email_id}, user '{user}': {e}")

async def log_document_action_db(
    db_pool: asyncpg.pool.Pool,
    document_id: int,
    action: str, # This is now the action description to be put in data
    user: str = "system_user",
    data: Optional[Dict[str, Any]] = None
) -> None:
    '''
    Logs a document-specific action to the audit_trail table.
    Document ID is now part of the 'data' dictionary.
    '''
    try:
        document_details = await db_pool.fetchrow(
            "SELECT filename, email_id FROM documents WHERE id = $1", document_id
        )
        document_filename = "N/A"
        email_id_for_context = None # For potential cross-referencing if needed in data
        if document_details:
            document_filename = document_details['filename']
            email_id_for_context = document_details['email_id']

        log_data = data if data is not None else {}
        log_data.update({
            "action_description": action, 
            "document_id": document_id, # Ensure document_id is in the data payload
            "email_id_context": email_id_for_context, # Optional: context for the document's email
            "document_filename": document_filename
        })

        await log_generic_action_db(
            db_pool,
            username=user,
            event_type="document_event", # Generic event_type for document-related logs
            data=log_data
        )
    except Exception as e:
        logger.error(f"Failed to log document action '{action}' for document {document_id}, user '{user}': {e}")

# --- User Management Functions ---
async def get_user_by_email_db(db_pool: asyncpg.pool.Pool, email: str) -> Optional[Dict[str, Any]]:
    '''
    Retrieves a user from the database by their email address.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email: The email address of the user to retrieve.
    :type email: str
    :returns: A dictionary containing user details if found, otherwise None.
    :rtype: Optional[Dict[str, Any]]
    '''
    row = await db_pool.fetchrow("SELECT id, email, is_admin, roles, google_id, created_at, updated_at, mcp_token, google_access_token, google_refresh_token FROM users WHERE email = $1", email)
    return dict(row) if row else None

async def get_user_by_id_db(db_pool: asyncpg.pool.Pool, user_id: int) -> Optional[Dict[str, Any]]:
    '''
    Retrieves a user from the database by their ID.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param user_id: The ID of the user to retrieve.
    :type user_id: int
    :returns: A dictionary containing user details if found, otherwise None.
    :rtype: Optional[Dict[str, Any]]
    '''
    row = await db_pool.fetchrow("SELECT id, email, is_admin, roles, google_id, created_at, updated_at, mcp_token, google_access_token, google_refresh_token FROM users WHERE id = $1", user_id)
    return dict(row) if row else None

async def create_user_db(
    db_pool: asyncpg.pool.Pool,
    email: str,
    hashed_password: str,
    is_admin: bool = False,
    roles: Optional[List[str]] = None,
    google_id: Optional[str] = None
) -> Dict[str, Any]:
    '''
    Creates a new user in the database.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email: The email address of the new user.
    :type email: str
    :param hashed_password: The hashed password for the new user.
    :type hashed_password: str
    :param is_admin: Flag indicating if the user is an administrator, defaults to False.
    :type is_admin: bool
    :param roles: Optional list of roles assigned to the user.
    :type roles: Optional[List[str]]
    :param google_id: Optional Google ID for the user.
    :type google_id: Optional[str]
    :raises Exception: If user creation fails in the database.
    :returns: A dictionary containing the details of the created user.
    :rtype: Dict[str, Any]
    '''
    roles_array = roles if roles else []
    row = await db_pool.fetchrow(
        """
        INSERT INTO users (email, password, is_admin, roles, google_id, google_access_token, google_refresh_token, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, NULL, NULL, NOW(), NOW())
        RETURNING id, email, is_admin, roles, google_id, created_at, updated_at, mcp_token, google_access_token, google_refresh_token
        """,
        email, hashed_password, is_admin, roles_array, google_id
    )
    if not row:
        raise Exception("Failed to create user due to an unexpected database error.")
    
    user_data = dict(row)
    user_data.setdefault('mcp_token', None)
    user_data.setdefault('google_access_token', None)
    user_data.setdefault('google_refresh_token', None)
    return user_data

async def update_user_db(
    db_pool: asyncpg.pool.Pool,
    user_identifier: Any, 
    updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    '''
    Updates user details in the database.

    The user can be identified by either their ID (int) or email (str).
    Valid fields for update are: "email", "password", "is_admin", "roles", "google_id", "mcp_token", "google_access_token", "google_refresh_token".

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param user_identifier: The ID (int) or email (str) of the user to update.
    :type user_identifier: Any
    :param updates: A dictionary containing the fields to update and their new values.
    :type updates: Dict[str, Any]
    :returns: A dictionary containing the updated user details if successful, otherwise None.
    :rtype: Optional[Dict[str, Any]]
    '''
    set_clauses = []
    values = []
    param_idx = 1

    for key, value in updates.items():
        if key in ["email", "password", "is_admin", "roles", "google_id", "mcp_token", "google_access_token", "google_refresh_token"]:
            set_clauses.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1
    
    if not set_clauses:
        logger.warning("No valid fields provided for user update.")
        if isinstance(user_identifier, int):
            return await get_user_by_id_db(db_pool, user_identifier)
        elif isinstance(user_identifier, str):
            return await get_user_by_email_db(db_pool, user_identifier)
        return None

    set_query_part = ", ".join(set_clauses)
    condition_column = "id" if isinstance(user_identifier, int) else "email"
    values.append(user_identifier)

    query = f"""
        UPDATE users SET {set_query_part}, updated_at = NOW()
        WHERE {condition_column} = ${param_idx}
        RETURNING id, email, is_admin, roles, google_id, created_at, updated_at, mcp_token, google_access_token, google_refresh_token
    """
    
    row = await db_pool.fetchrow(query, *values)
    if not row:
        return None
    
    user_data = dict(row)
    user_data.setdefault('mcp_token', None)
    user_data.setdefault('google_access_token', None)
    user_data.setdefault('google_refresh_token', None)
    return user_data

async def delete_user_db(db_pool: asyncpg.pool.Pool, user_identifier: Any) -> bool:
    '''
    Deletes a user from the database.

    The user can be identified by either their ID (int) or email (str).

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param user_identifier: The ID (int) or email (str) of the user to delete.
    :type user_identifier: Any
    :returns: True if the user was deleted successfully, False otherwise.
    :rtype: bool
    '''
    condition_column = "id" if isinstance(user_identifier, int) else "email"
    query = f"DELETE FROM users WHERE {condition_column} = $1"
    result = await db_pool.execute(query, user_identifier)
    return result == "DELETE 1"

async def list_users_db(db_pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    '''
    Lists all users from the database, ordered by email.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A list of dictionaries, where each dictionary contains user details.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch("SELECT id, email, is_admin, roles, google_id, created_at, updated_at, mcp_token, google_access_token, google_refresh_token FROM users ORDER BY email")
    users = []
    for row in rows:
        user_data = dict(row)
        user_data.setdefault('mcp_token', None)
        user_data.setdefault('google_access_token', None)
        user_data.setdefault('google_refresh_token', None)
        users.append(user_data)
    return users

async def get_user_access_token_db(db_pool: asyncpg.pool.Pool, user_email: str) -> Optional[str]:
    '''
    Retrieves the Google access token for a given user by email.

    If the specified user is not found or has no token, it attempts a fallback
    to find any user with a Google access token (this fallback behavior might be reviewed).

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param user_email: The email address of the user.
    :type user_email: str
    :returns: The Google access token if found, otherwise None.
    :rtype: Optional[str]
    '''
    user_row = await db_pool.fetchrow("SELECT google_access_token FROM users WHERE email = $1", user_email)
    # Fallback to original logic if specific user not found or has no token, though this might not be desired.
    if not user_row or not user_row['google_access_token']:
        logger.warning(f"Google access token not found for user: {user_email}. Trying to find any token as fallback.")
        user_row = await db_pool.fetchrow("SELECT google_access_token FROM users WHERE google_access_token IS NOT NULL LIMIT 1")

    if user_row and user_row['google_access_token']:
        return user_row['google_access_token']
    logger.error(f"No Google access token found for user {user_email} or any user.")
    return None


async def update_user_google_tokens_db(db_pool: asyncpg.pool.Pool, user_id: int, access_token: str, refresh_token: Optional[str]) -> None:
    '''
    Updates the Google OAuth tokens for a user.

    The refresh token is only updated if a new value is provided.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param user_id: The ID of the user whose tokens are to be updated.
    :type user_id: int
    :param access_token: The new Google access token.
    :type access_token: str
    :param refresh_token: The new Google refresh token (optional). If None, existing refresh token is kept.
    :type refresh_token: Optional[str]
    :returns: None
    :rtype: None
    '''
    await db_pool.execute(
        "UPDATE users SET google_access_token = $1, google_refresh_token = COALESCE($2, google_refresh_token), updated_at = NOW() WHERE id = $3",
        access_token, refresh_token, user_id
    )

async def update_user_mcp_token_db(db_pool: asyncpg.pool.Pool, user_email: str, mcp_token: str) -> bool:
    '''
    Updates the MCP token for a user identified by their email.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param user_email: The email address of the user.
    :type user_email: str
    :param mcp_token: The new MCP token.
    :type mcp_token: str
    :returns: True if the update was successful (one row affected), False otherwise.
    :rtype: bool
    '''
    result = await db_pool.execute(
        "UPDATE users SET mcp_token = $1, updated_at = NOW() WHERE email = $2",
        mcp_token, user_email
    )
    return result == "UPDATE 1"

# --- Email Management Functions ---
async def get_emails_db(db_pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    '''
    Retrieves all emails from the database, ordered by received date descending.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A list of dictionaries, where each dictionary contains email details.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch("SELECT id, subject, sender, body, received_at, label, type, short_description, document_ids FROM emails ORDER BY received_at DESC")
    return [dict(row) for row in rows]

async def get_email_by_id_db(db_pool: asyncpg.pool.Pool, email_id: int) -> Optional[Dict[str, Any]]:
    '''
    Retrieves a specific email from the database by its ID.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email to retrieve.
    :type email_id: int
    :returns: A dictionary containing email details if found, otherwise None.
    :rtype: Optional[Dict[str, Any]]
    '''
    row = await db_pool.fetchrow("SELECT id, subject, sender, body, received_at, label, type, short_description, document_ids FROM emails WHERE id = $1", email_id)
    return dict(row) if row else None

async def update_email_label_db(db_pool: asyncpg.pool.Pool, email_id: int, label: str) -> bool:
    '''
    Updates the label of a specific email.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email to update.
    :type email_id: int
    :param label: The new label for the email.
    :type label: str
    :returns: True if the update was successful (one row affected), False otherwise.
    :rtype: bool
    '''
    result = await db_pool.execute("UPDATE emails SET label = $1, updated_at = NOW() WHERE id = $2", label, email_id)
    return result == "UPDATE 1"

async def delete_email_from_db(db_pool: asyncpg.pool.Pool, email_id: int) -> bool:
    '''
    Deletes an email and its associated data (tasks, documents, audit trail entries) from the database.

    This operation is performed within a transaction.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email to delete.
    :type email_id: int
    :returns: True if the email was deleted successfully, False otherwise.
    :rtype: bool
    '''
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM tasks WHERE email_id = $1", email_id)
            await conn.execute("DELETE FROM documents WHERE email_id = $1", email_id)
            # Audit trail entries related to this email are now identified by email_id within the 'data' field.
            # A more complex query would be needed to delete them if strictly necessary, or they can be kept.
            # For simplicity, we are not deleting audit_trail entries based on email_id in data field here.
            # If you need to delete them, you'd query: DELETE FROM audit_trail WHERE data->>'email_id' = email_id::text;
            result = await conn.execute("DELETE FROM emails WHERE id = $1", email_id)
            
            await log_generic_action_db(
                db_pool=conn, 
                username="user_api", 
                event_type="email_deletion_event", 
                data={
                    "action_description": f"Email and associated data deleted from database.",
                    "deleted_email_id": email_id
                }
            )
            return result == "DELETE 1"

async def get_documents_by_email_id_db(
    db_pool: asyncpg.pool.Pool,
    email_id: int
) -> List[Dict[str, Any]]:
    '''
    Retrieves all documents associated with a specific email ID.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email whose documents to retrieve.
    :type email_id: int
    :returns: A list of dictionaries, where each dictionary contains document details.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch("SELECT id, filename, content_type, is_processed, created_at, updated_at, processed_data FROM documents WHERE email_id = $1", email_id)
    return [dict(row) for row in rows]

# --- Document Management Functions ---
async def get_documents_db(db_pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    '''
    Retrieves all documents from the database, ordered by creation date descending.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A list of dictionaries, where each dictionary contains document details.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch("SELECT * FROM documents")
    return [dict(row) for row in rows]

async def get_document_content_db(db_pool: asyncpg.pool.Pool, document_id: int) -> Optional[Dict[str, Any]]:
    '''
    Retrieves specific details of a document, including its base64 encoded data.

    Fields returned: id, filename, content_type, data_b64, processed_data.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param document_id: The ID of the document to retrieve.
    :type document_id: int
    :returns: A dictionary containing document details if found, otherwise None.
    :rtype: Optional[Dict[str, Any]]
    '''
    row = await db_pool.fetchrow("SELECT id, filename, content_type, data_b64, processed_data FROM documents WHERE id = $1", document_id)
    return dict(row) if row else None
    
async def create_document_db(
    db_pool: asyncpg.pool.Pool,
    email_id: int,
    filename: str,
    content_type: str,
    data_b64: str,
    created_at_dt: Optional[datetime.datetime] = None,
    processed_data: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    '''
    Creates a new document record in the database and returns the created record (excluding data_b64).
    Logs the creation of the document.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email this document is associated with.
    :type email_id: int
    :param filename: The name of the document file.
    :type filename: str
    :param content_type: The MIME type of the document.
    :type content_type: str
    :param data_b64: The base64 encoded content of the document.
    :type data_b64: str
    :param created_at_dt: Optional datetime for when the document was created.
                          If timezone-aware, it will be converted to naive UTC. Defaults to NOW().
    :type created_at_dt: Optional[datetime.datetime]
    :param processed_data: Optional string containing processed data from the document.
    :type processed_data: Optional[str]
    :returns: A dictionary containing the details of the created document (excluding data_b64) if successful, otherwise None.
    :rtype: Optional[Dict[str, Any]]
    '''
    final_created_at = created_at_dt
    # Assuming 'created_at' column in 'documents' table is 'timestamp without time zone'
    # based on behavior in existing insert_document_db.
    if final_created_at and final_created_at.tzinfo is not None:
        final_created_at = final_created_at.replace(tzinfo=None)

    query = """
        INSERT INTO documents (email_id, filename, content_type, data_b64, is_processed, created_at, updated_at, processed_data)
        VALUES ($1, $2, $3, $4, FALSE, COALESCE($5, NOW()), NOW(), $6)
        RETURNING id, email_id, filename, content_type, is_processed, created_at, updated_at, processed_data
    """
    try:
        row = await db_pool.fetchrow(
            query,
            email_id,
            filename,
            content_type,
            data_b64,
            final_created_at,
            processed_data
        )
        if row:
            doc_id = row['id']
            await log_generic_action_db(
                db_pool,
                username="system_document_creation",
                event_type="document_creation_event",
                data={
                    "action_description": f"Document '{filename}' (ID: {doc_id}) created and associated with email ID {email_id}.",
                    "document_id": doc_id,
                    "email_id": email_id,
                    "filename": filename,
                    "content_type": content_type
                }
            )
            return dict(row)
        else:
            logger.error(f"Document creation failed for '{filename}' with email ID {email_id}, no row returned.")
            return None
    except Exception as e:
        logger.error(f"Exception during document creation for '{filename}' with email ID {email_id}: {e}")
        return None

async def delete_document_from_db(db_pool: asyncpg.pool.Pool, document_id: int) -> bool:
    '''
    Deletes a document from the database and updates associated email records.

    This operation is performed within a transaction. It also deletes related audit trail entries
    and removes the document ID from the `document_ids` array in the `emails` table.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param document_id: The ID of the document to delete.
    :type document_id: int
    :returns: True if the document was deleted successfully, False otherwise.
    :rtype: bool
    '''
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Audit trail entries related to this document are now identified by document_id within the 'data' field.
            # Similar to email deletion, not deleting them here for simplicity.
            result = await conn.execute("DELETE FROM documents WHERE id = $1", document_id)
            await conn.execute(
                "UPDATE emails SET document_ids = array_remove(document_ids, $1) WHERE $1 = ANY(document_ids)",
                document_id
            )
            await log_generic_action_db(
                db_pool=conn, 
                username="system_document_deletion",
                event_type="document_deletion_event", 
                data={
                    "action_description": f"Document deleted from database.",
                    "deleted_document_id": document_id
                } 
            )
            return result == "DELETE 1"

async def delete_email_and_audit_for_duplicate_db(db_pool: asyncpg.pool.Pool, email_id: int, original_subject: str) -> None:
    '''
    Deletes an email identified as a duplicate and its associated processing tasks.
    Logs the deletion of the duplicate.
    '''
    async with db_pool.acquire() as connection:
        async with connection.transaction():
            # First, delete associated tasks from the 'tasks' table
            await connection.execute("DELETE FROM tasks WHERE email_id = $1", email_id)
            logger.info(f"Deleted tasks associated with duplicate email ID: {email_id}")

            # Then, delete the email itself
            await connection.execute("DELETE FROM emails WHERE id = $1", email_id)
            logger.info(f"Deleted duplicate email ID: {email_id} (Subject: '{original_subject}')")
            
            await log_generic_action_db(
                db_pool=connection, 
                username="system_email_processing",
                event_type="duplicate_email_deletion_event", 
                data={
                    "action_description": f"Duplicate email (DB ID: {email_id}, Subject: '{original_subject}') and associated tasks deleted.",
                    "deleted_email_id": email_id,
                    "original_subject": original_subject
                }
            )

# --- Settings Functions ---
async def get_settings_db(db_pool: asyncpg.pool.Pool) -> Dict[str, Any]:
    '''
    Retrieves various application settings from the database.

    This includes email grabber frequency, email types, and key features.
    Default values are provided for email grabber frequency if not found in the database.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A dictionary containing various settings.
    :rtype: Dict[str, Any]
    '''
    settings_map = {}
    keys_to_fetch = [
        'email_grabber_frequency_type', 
        'email_grabber_frequency_value',
    ]
    for key in keys_to_fetch:
        row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        settings_map[key] = row['value'] if row else None

    email_types_rows = await db_pool.fetch("SELECT id, topic, description FROM email_types ORDER BY topic")
    settings_map['email_types'] = [dict(row) for row in email_types_rows]

    key_features_rows = await db_pool.fetch("SELECT id, name FROM key_features ORDER BY name")
    settings_map['key_features'] = [dict(row) for row in key_features_rows]
    
    settings_map.setdefault('email_grabber_frequency_type', 'days')
    settings_map.setdefault('email_grabber_frequency_value', '1')
    
    return settings_map

async def save_settings_db(db_pool: asyncpg.pool.Pool, settings_data_dict: Dict[str, Any]) -> None:
    '''
    Saves application settings to the database.

    This includes email grabber frequency, email types, and key features.
    Existing email types and key features are deleted and replaced with the new ones.
    This operation is performed within a transaction.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param settings_data_dict: A dictionary containing the settings to save.
                               Expected keys: 'email_grabber_frequency_type', 'email_grabber_frequency_value',
                               'email_types' (list of dicts), 'key_features' (list of dicts).
    :type settings_data_dict: Dict[str, Any]
    :returns: None
    :rtype: None
    '''
    async with db_pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                'email_grabber_frequency_type', settings_data_dict.get('email_grabber_frequency_type')
            )
            await connection.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                'email_grabber_frequency_value', str(settings_data_dict.get('email_grabber_frequency_value'))
            )

            await connection.execute("DELETE FROM email_types")
            email_types_to_insert = settings_data_dict.get('email_types', [])
            if email_types_to_insert:
                email_type_values = [(et.get('topic'), et.get('description')) for et in email_types_to_insert]
                if email_type_values:
                    await connection.copy_records_to_table('email_types', records=email_type_values, columns=['topic', 'description']) # Overwrite, removed if_not_exists

            await connection.execute("DELETE FROM key_features")
            key_features_to_insert = settings_data_dict.get('key_features', [])
            if key_features_to_insert:
                key_feature_values = [(kf.get('name'),) for kf in key_features_to_insert]
                if key_feature_values:
                     await connection.copy_records_to_table('key_features', records=key_feature_values, columns=['name']) # Overwrite

# --- SchedulerTask / Workflow Functions ---
async def get_scheduler_tasks_db(db_pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    '''
    Retrieves all scheduler tasks (workflows) from the database, ordered by creation date descending.

    Workflow configuration stored as JSON in the database is parsed into a dictionary.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A list of dictionaries, where each dictionary represents a scheduler task.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch(
        """
        SELECT id, task_name, type, description, status, workflow_config, created_at, updated_at
        FROM scheduler_tasks ORDER BY created_at DESC
        """
    )
    results = []
    for row in rows:
        task = dict(row)
        if task.get('workflow_config') and isinstance(task['workflow_config'], str):
            try:
                task['workflow_config'] = json.loads(task['workflow_config'])
            except json.JSONDecodeError:
                task['workflow_config'] = {}
        results.append(task)
    return results


async def create_scheduler_task_db(db_pool: asyncpg.pool.Pool, task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    '''
    Creates a new scheduler task (workflow) in the database.

    Workflow configuration is stored as a JSON string.
    Logs the creation of the scheduler task.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param task_data: A dictionary containing data for the new task.
                      Expected keys: 'task_name', 'trigger_type', 'type', 'description',
                      'status' (optional, defaults to 'active'), 'workflow_config' (dict, optional).
    :type task_data: Dict[str, Any]
    :returns: A dictionary representing the created scheduler task if successful, otherwise None.
              The 'workflow_config' in the returned dict is parsed into a Python dict.
    :rtype: Optional[Dict[str, Any]]
    '''
    workflow_config_json = task_data.get('workflow_config')
    if isinstance(workflow_config_json, dict):
        workflow_config_json = json.dumps(workflow_config_json)
    elif workflow_config_json is None:
        workflow_config_json = json.dumps({}) # Default to empty JSON object if None
    
    task_uuid = str(uuid.uuid4()) # Generate a unique ID
    logger.info(f"Creating scheduler task with ID: {task_uuid}, data: {task_data}, workflow_config_json: {workflow_config_json}")
    logger.debug(f"Creating scheduler task with ID: {task_uuid}, data: {task_data}, workflow_config_json: {workflow_config_json}")
    # Ensure all NOT NULL columns are included and names match db_init.sql
    # id is TEXT PRIMARY KEY, type and description are TEXT NOT NULL
    query = """
        INSERT INTO scheduler_tasks
            (id, task_name, type, description, status, workflow_config, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
        RETURNING id, task_name, type, description, status, last_run_at, workflow_config, created_at, updated_at
    """ # Removed next_run_at, trigger_type from RETURNING
    try:
        # Ensure 'type' and 'description' are provided, as they are NOT NULL in the table
        task_type = task_data.get('type')
        task_description = task_data.get('description')

        # Removed trigger_type from parameters as it's removed from the table
        row = await db_pool.fetchrow(
            query,
            task_uuid,                           # $1 - id
            task_data.get('task_name'),          # $2 - task_name
            task_type,                           # $3 - type (ensure this is not None)
            task_description,                    # $4 - description (ensure this is not None)
            task_data.get('status', 'active'),   # $5 - status
            workflow_config_json,                # $6 - workflow_config
        )
        
        if not row:
            logger.error(f"Scheduler task creation failed for task_name: {task_data.get('task_name')} with generated ID {task_uuid}. No row returned.")
            return None
        
        created_task = dict(row)
        # Ensure workflow_config is a dict in the returned object
        if created_task.get('workflow_config') and isinstance(created_task['workflow_config'], str):
            try:
                created_task['workflow_config'] = json.loads(created_task['workflow_config'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse workflow_config JSON for newly created task ID {created_task.get('id')}")
                created_task['workflow_config'] = {} # Default to empty dict on error
        elif created_task.get('workflow_config') is None:
             created_task['workflow_config'] = {}

        # Log the creation using a generic action with event_type
        await log_generic_action_db(
            db_pool,
            username="system_scheduler_task_creation",
            event_type="scheduler_task_creation",
            data={
                "action_description": f"Scheduler task created.",
                "scheduler_task_id": created_task.get('id'),
                "task_name": created_task.get('task_name')
            }
        )
        return created_task
    except Exception as e:
        logger.error(f"Exception during scheduler task creation for task_name: {task_data.get('task_name')}: {e}")
        return None

async def update_scheduler_task_db(db_pool: asyncpg.pool.Pool, task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    '''
    Updates an existing scheduler task (workflow) in the database.

    Valid fields for update: "task_name", "type", "description", "status",
    "workflow_config", "last_run_at".
    Workflow configuration is stored as a JSON string.
    Logs the update action.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param task_id: The ID of the scheduler task to update.
    :type task_id: int
    :param updates: A dictionary containing the fields to update and their new values.
    :type updates: Dict[str, Any]
    :returns: A dictionary representing the updated scheduler task if successful, otherwise None.
              The 'workflow_config' in the returned dict is parsed into a Python dict.
    :rtype: Optional[Dict[str, Any]]
    '''
    set_clauses = []
    values = []
    param_idx = 1

    for key, value in updates.items():
        # Removed trigger_type, cron_expression, next_run_at from updatable fields
        if key in ["task_name", "type", "description", "status", "workflow_config", "last_run_at"]:
            if key == "workflow_config" and isinstance(value, dict):
                value = json.dumps(value)
            elif key in ["last_run_at"] and value is None: # Allow setting to NULL
                pass # Handled by COALESCE or direct assignment if needed
            elif key in ["last_run_at"] and not isinstance(value, datetime.datetime):
                try:
                    value = datetime.datetime.fromisoformat(str(value))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid datetime format for {key}: {value}. Skipping update for this field.")
                    continue
            
            set_clauses.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1
    
    if not set_clauses:
        logger.warning(f"No valid fields provided for scheduler task update (ID: {task_id}).")
        # Optionally, fetch and return the current task state
        current_task_row = await db_pool.fetchrow("SELECT id, task_name, trigger_type, cron_expression, status, last_run_at, next_run_at, workflow_config, created_at, updated_at FROM scheduler_tasks WHERE id = $1", task_id)
        if current_task_row:
            current_task = dict(current_task_row)
            if current_task.get('workflow_config') and isinstance(current_task['workflow_config'], str):
                try: current_task['workflow_config'] = json.loads(current_task['workflow_config'])
                except: current_task['workflow_config'] = {}
            return current_task
        return None

    set_query_part = ", ".join(set_clauses)
    values.append(task_id) # For the WHERE id = $param_idx

    query = f"""
        UPDATE scheduler_tasks SET {set_query_part}, updated_at = NOW()
        WHERE id = ${param_idx}
        RETURNING id, task_name, type, description, status, last_run_at, workflow_config, created_at, updated_at
    """ # Removed next_run_at, trigger_type from RETURNING
    
    row = await db_pool.fetchrow(query, *values)
        
    if not row:
        logger.error(f"Scheduler task update failed for ID: {task_id}. No row returned.")
        return None
    
    updated_task = dict(row)
    if updated_task.get('workflow_config') and isinstance(updated_task['workflow_config'], str):
        try: 
            updated_task['workflow_config'] = json.loads(updated_task['workflow_config'])
        except json.JSONDecodeError:
            logger.error(f"Failed to parse workflow_config JSON for updated task ID {updated_task.get('id')}")
            updated_task['workflow_config'] = {}
    elif updated_task.get('workflow_config') is None:
        updated_task['workflow_config'] = {}
    
    # Log the update using a generic action with event_type
    await log_generic_action_db(
        db_pool,
        username="system_scheduler_task_update",
        event_type="scheduler_task_update", # Specific event type
        data={
            "action_description": f"Scheduler task updated.",
            "scheduler_task_id": updated_task.get('id'),
            "updated_fields": list(updates.keys())
        } # Include action description and details in data
    )
    return updated_task

async def delete_scheduler_task_db(db_pool: asyncpg.pool.Pool, task_id: int) -> bool:
    '''
    Deletes a scheduler task from the database.

    Logs the deletion action.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param task_id: The ID of the scheduler task to delete.
    :type task_id: int
    :returns: True if the task was deleted successfully, False otherwise.
    :rtype: bool
    '''
    try:
        result = await db_pool.execute("DELETE FROM scheduler_tasks WHERE id = $1", task_id)
        if result == "DELETE 1":
            # Log the deletion
            await log_generic_action_db(
                db_pool,
                username="system_scheduler_task_deletion",
                event_type="scheduler_task_deletion",
                data={
                    "action_description": f"Scheduler task ID {task_id} deleted.",
                    "deleted_scheduler_task_id": task_id
                }
            )
            logger.info(f"Scheduler task ID {task_id} successfully deleted.")
            return True
        else:
            logger.warning(f"Failed to delete scheduler task ID {task_id}. Task not found or no change made.")
            return False
    except Exception as e:
        logger.error(f"Exception deleting scheduler task ID {task_id}: {e}")
        return False

# --- ProcessingTask Functions ---
async def get_processing_tasks_db(db_pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    '''
    Retrieves processing tasks along with associated email details from the database.

    Tasks are ordered by creation date descending.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A list of dictionaries, where each dictionary represents a processing task
              and includes details from the associated email.
    :rtype: List[Dict[str, Any]]
    '''
    query = """
        SELECT 
            t.id, t.email_id, t.status, t.created_at, t.updated_at, t.workflow_type,
            e.subject AS email_subject, e.sender AS email_sender,
            e.body AS email_body, e.received_at AS email_received_at,
            e.label AS email_label, e.short_description AS email_short_description
        FROM tasks t
        LEFT JOIN emails e ON t.email_id = e.id
        ORDER BY t.created_at DESC
    """
    rows = await db_pool.fetch(query)
    tasks_data = []
    for row_proxy in rows:
        row_dict = dict(row_proxy)
        row_dict.setdefault('email_subject', None)
        row_dict.setdefault('email_sender', None)
        row_dict.setdefault('email_body', None) 
        row_dict.setdefault('email_received_at', None)
        row_dict.setdefault('email_label', None)
        row_dict.setdefault('email_short_description', None)
        row_dict.setdefault('workflow_type', None)
        tasks_data.append(row_dict)
    return tasks_data

async def update_task_status_db(db_pool: asyncpg.pool.Pool, task_id: int, status: str, user: str = "system_user") -> bool:
    '''
    Updates the status of a processing task.

    Logs the status change action.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param task_id: The ID of the task to update.
    :type task_id: int
    :param status: The new status for the task.
    :type status: str
    :param user: The user initiating the status change, defaults to "system_user".
    :type user: str
    :returns: True if the update was successful (one row affected), False otherwise.
    :rtype: bool
    '''
    result = await db_pool.execute(
        "UPDATE tasks SET status = $1, updated_at = NOW() WHERE id = $2",
        status, task_id
    )
    if result == "UPDATE 1":
        # Use the updated log_task_action_db which now accepts data
        await log_task_action_db(db_pool, task_id, f"Status changed to {status}", user, data={"new_status": status})
        return True
    return False

# --- Functions for agent/email_checker.py ---
async def find_existing_email_db(db_pool: asyncpg.pool.Pool, subject: str, sender: str, body: str) -> Optional[int]:
    '''
    Finds an existing email by its subject, sender, and body to detect duplicates.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param subject: The subject of the email.
    :type subject: str
    :param sender: The sender of the email.
    :type sender: str
    :param body: The body content of the email.
    :type body: str
    :returns: The ID of the existing email if found, otherwise None.
    :rtype: Optional[int]
    '''
    return await db_pool.fetchval(
        "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3",
        subject, sender, body
    )

async def delete_email_and_audit_for_duplicate_db(db_pool: asyncpg.pool.Pool, email_id: int, original_subject: str) -> None:
    '''
    Deletes an email identified as a duplicate and its associated processing tasks.
    Logs the deletion of the duplicate.
    '''
    async with db_pool.acquire() as connection:
        async with connection.transaction():
            # First, delete associated tasks from the 'tasks' table
            await connection.execute("DELETE FROM tasks WHERE email_id = $1", email_id)
            logger.info(f"Deleted tasks associated with duplicate email ID: {email_id}")

            # Then, delete the email itself
            await connection.execute("DELETE FROM emails WHERE id = $1", email_id)
            logger.info(f"Deleted duplicate email ID: {email_id} (Subject: '{original_subject}')")
            
            await log_generic_action_db(
                db_pool=connection, 
                username="system_email_processing",
                event_type="duplicate_email_deletion_event", 
                data={
                    "action_description": f"Duplicate email (DB ID: {email_id}, Subject: '{original_subject}') and associated tasks deleted.",
                    "deleted_email_id": email_id,
                    "original_subject": original_subject
                }
            )

async def insert_new_email_db(
    db_pool: asyncpg.pool.Pool,
    subject: str,
    sender: str, # Parsed email address
    body: str,
    received_at: datetime.datetime, # Should be timezone-aware or consistently naive UTC
    label: Optional[str],
    email_type: Optional[str], 
    short_description: Optional[str],
    document_ids: Optional[List[int]] = None # List of document IDs
) -> int:
    '''
    Inserts a new email into the database.

    The `received_at` datetime might be adjusted to naive if the database column
    is 'timestamp without time zone'.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param subject: The subject of the email.
    :type subject: str
    :param sender: The parsed email address of the sender.
    :type sender: str
    :param body: The body content of the email.
    :type body: str
    :param received_at: The datetime when the email was received.
                        Should be timezone-aware or consistently naive UTC.
    :type received_at: datetime.datetime
    :param label: Optional label for the email.
    :type label: Optional[str]
    :param email_type: Optional type classification for the email.
    :type email_type: Optional[str]
    :param short_description: Optional short description of the email content.
    :type short_description: Optional[str]
    :param document_ids: Optional list of document IDs associated with this email.
    :type document_ids: Optional[List[int]]
    :returns: The ID of the newly inserted email.
    :rtype: int
    '''
    # Ensure received_at is naive if your DB column is timestamp without timezone, or aware if it is with timezone
    # Assuming DB 'received_at' is 'timestamp without time zone' and 'created_at', 'updated_at' are 'timestamp with time zone' (or use NOW())
    if received_at.tzinfo is not None:
        received_at = received_at.replace(tzinfo=None) # Example: Convert to naive for 'timestamp without time zone'

    return await db_pool.fetchval(
        """
        INSERT INTO emails (subject, sender, body, received_at, label, type, short_description, document_ids)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        subject, sender, body, received_at, label, email_type, short_description, document_ids
    )

async def insert_document_db(
    db_pool: asyncpg.pool.Pool,
    email_id: int,
    filename: str,
    content_type: str,
    data_b64: str, 
    created_at_dt: datetime.datetime, # Should match email's received_at or be NOW()
    processed_data: Optional[str] = None # New field
) -> int:
    '''
    Inserts a new document associated with an email into the database.

    The `created_at_dt` datetime might be adjusted to naive if the database column
    is 'timestamp without time zone'.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email this document belongs to.
    :type email_id: int
    :param filename: The name of the document file.
    :type filename: str
    :param content_type: The MIME type of the document.
    :type content_type: str
    :param data_b64: The base64 encoded content of the document.
    :type data_b64: str
    :param created_at_dt: The datetime when the document was created/received.
                          Should match the email's `received_at` or be current time.
    :type created_at_dt: datetime.datetime
    :param processed_data: Optional string containing processed data from the document.
    :type processed_data: Optional[str]
    :returns: The ID of the newly inserted document.
    :rtype: int
    '''
    if created_at_dt.tzinfo is not None:
         created_at_dt = created_at_dt.replace(tzinfo=None) # Match 'timestamp without time zone' if that's the column type

    return await db_pool.fetchval(
        """
        INSERT INTO documents (email_id, filename, content_type, data_b64, is_processed, created_at, updated_at, processed_data)
        VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
        RETURNING id
        """,
        email_id, filename, content_type, data_b64, False, created_at_dt, processed_data # New field
    )

async def update_email_document_ids_db(
    db_pool: asyncpg.pool.Pool,
    email_id: int,
    document_ids: List[int]
) -> bool:
    '''
    Updates the document_ids array for a given email.

    Logs the action, whether successful or failed.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email to update.
    :type email_id: int
    :param document_ids: The new list of document IDs for the email.
    :type document_ids: List[int]
    :returns: True if the update was successful, False otherwise.
    :rtype: bool
    '''
    try:
        result = await db_pool.execute(
            "UPDATE emails SET document_ids = $1, updated_at = NOW() WHERE id = $2",
            document_ids, email_id
        )
        if result == "UPDATE 1":
            # Log success
            await log_email_action_db(
                db_pool,
                email_id=email_id,
                action="Document IDs updated",
                user="system_processing", # Or derive user
                data={"new_document_ids": document_ids}
            )
            logger.info(f"Email ID {email_id} document_ids successfully updated.")
            return True
        else:
            # Log failure if email_id not found or no change
            await log_email_action_db(
                db_pool,
                email_id=email_id,
                action="Failed to update document IDs for email",
                user="system_processing",
                data={"error": f"Update query returned: {result}", "document_ids_attempted": document_ids}
            )
            
            logger.warning(f"Failed to update document_ids for email ID {email_id}. Result: {result}")
            return False
    except Exception as e:
        # Log exception
        await log_email_action_db(
            db_pool,
            email_id=email_id,
            action="Exception updating document IDs",
            user="system_processing",
            data={"error": str(e), "document_ids_attempted": document_ids}
        )
        return False

async def update_document_processed_data_db(
    db_pool: asyncpg.pool.Pool,
    document_id: int,
    processed_data_text: str,
    username: str = "system_processing"
) -> bool:
    '''
    Updates an existing document with processed data and marks it as processed.
    Logs the update action.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param document_id: The ID of the document to update.
    :type document_id: int
    :param processed_data_text: The processed text data from the document.
    :type processed_data_text: str
    :param username: The username performing the update, defaults to "system_processing".
    :type username: str
    :returns: True if the update was successful, False otherwise.
    :rtype: bool
    '''
    try:
        result = await db_pool.execute(
            """
            UPDATE documents
            SET processed_data = $1, is_processed = TRUE, updated_at = NOW()
            WHERE id = $2
            """,
            processed_data_text, document_id
        )
        if result == "UPDATE 1":
            # Log the update using the new wrapper
            await log_document_action_db(
                db_pool,
                document_id=document_id,
                action="Document marked as processed",
                user=username,
                data={"processed_data": processed_data_text} # Include processed data in log
            )
            return True
        else:
            await log_document_action_db(
                db_pool,
                document_id=document_id,
                action="Failed to update document as processed",
                user=username,
                data={"error": "No rows updated, document may not exist or already processed."}
            )
            return False
    except Exception as e:
        logger.error(f"Exception updating document ID {document_id} with processed data: {e}")
        return False

async def fetch_active_workflows_db(db_pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    '''
    Fetches active workflows (scheduler tasks) from the database.
    Now fetches all active workflows as trigger_type is removed.

    Workflow configuration JSON is parsed into a dictionary.
    Logs an error if parsing workflow_config JSON fails for a task.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :returns: A list of dictionaries, where each dictionary represents an active workflow.
              'workflow_config' is a Python dict.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch(
        "SELECT id, task_name, type, description, status, workflow_config, created_at, updated_at, last_run_at FROM scheduler_tasks WHERE status = 'active'" 
        # Removed trigger_type from query and parameters
    )
    results = []
    for row in rows:
        data = dict(row)
        config_str = data.get('workflow_config')
        if config_str and isinstance(config_str, str):
            try:
                data['workflow_config'] = json.loads(config_str)
            except json.JSONDecodeError:
                await log_task_action_db(
                    db_pool,
                    task_id=data.get('id'),
                    action="Failed to parse workflow_config JSON",
                    user="system_workflow_fetch",
                    data={"error": "Invalid JSON format in workflow_config", "task_name": data.get('task_name')}
                )
                data['workflow_config'] = {}
        elif not config_str: # Handles None or empty string
             data['workflow_config'] = {}
        # If it's already a dict (e.g. if DB returns JSON type directly), it's fine.
        results.append(data)
    return results


async def create_processing_task_db(
    db_pool: asyncpg.pool.Pool,
    email_id: int,
    initial_status: str,
    # created_at will be NOW() in the DB query
    workflow_type: Optional[str] 
) -> int:
    '''
    Creates a new processing task for an email, typically triggered by a workflow.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email_id: The ID of the email for which the task is created.
    :type email_id: int
    :param initial_status: The initial status of the task (e.g., 'new').
    :type initial_status: str
    :param workflow_type: Optional type of the workflow that initiated this task.
    :type workflow_type: Optional[str]
    :returns: The ID of the newly created processing task.
    :rtype: int
    '''
    return await db_pool.fetchval(
        """
        INSERT INTO tasks (email_id, status, created_at, updated_at, workflow_type)
        VALUES ($1, $2, NOW(), NOW(), $3) 
        RETURNING id
        """,
        email_id, initial_status, workflow_type
    )

async def get_audit_trail_db(db_pool: asyncpg.pool.Pool, limit: int = 50) -> List[Dict[str, Any]]:
    '''
    Retrieves the latest audit trail entries from the database.
    The 'data' field (JSONB from DB) is parsed into a Python dict.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param limit: The maximum number of audit entries to retrieve, defaults to 50.
    :type limit: int
    :returns: A list of dictionaries, where each dictionary represents an audit trail entry.
              The 'data' field (JSONB from DB) is parsed into a Python dict.
              The 'event_type' field is used directly as is from the DB.
    :rtype: List[Dict[str, Any]]
    '''
    rows = await db_pool.fetch(
        """
        SELECT id, event_type, username, timestamp, data
        FROM audit_trail
        ORDER BY timestamp DESC
        LIMIT $1
        """,
        limit
    )
    
    processed_rows = []
    for row_proxy in rows:
        row = dict(row_proxy)
        if row.get('data') and isinstance(row['data'], str):
            try:
                row['data'] = json.loads(row['data'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON for audit trail data: {row['data']}")
                row['data'] = {} # Default to empty dict on error
        elif row.get('data') is None: # Handle cases where data might be NULL in DB
            row['data'] = {}
        
        # event_type is now directly used by the Pydantic model, no renaming needed.
        # Ensure event_type exists, or provide a default if it can be NULL in DB
        # (though it's not defined as nullable in your db_init.sql for audit_trail)
        if 'event_type' not in row or row['event_type'] is None:
            row['event_type'] = "unknown_event" # Fallback if necessary
            
        processed_rows.append(row)
    return processed_rows

async def check_if_admin_user_exists_db(db_pool: asyncpg.pool.Pool, email: str) -> bool: # Original type hint was bool, but returns dict
    '''
    Checks if an admin user exists with the given email.

    Note: The return type annotation was `bool` but the implementation returns a dictionary.
    This docstring reflects the implementation.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email: The email address to check.
    :type email: str
    :returns: A dictionary with 'is_admin', 'roles', and 'google_id' if the user is an admin.
              Otherwise, a dictionary indicating not an admin with default values.
    :rtype: Dict[str, Any]
    '''
    # The original function signature returns bool, but the implementation returns a dict.
    # Keeping the implementation's return type for now.
    user_details = await db_pool.fetchrow("SELECT is_admin, roles, google_id FROM users WHERE email = $1 AND is_admin = TRUE", email)
    if not user_details:
        # Return a default structure if user not found or not admin
        return {"is_admin": False, "roles": [], "google_id": None}
    else:
        return {"is_admin": user_details["is_admin"], "roles": user_details["roles"], "google_id": user_details["google_id"]}


async def check_if_user_exists_db(db_pool: asyncpg.pool.Pool, email: str) -> bool:
    '''
    Checks if a user exists with the given email address.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param email: The email address to check.
    :type email: str
    :returns: True if a user with the email exists, False otherwise.
    :rtype: bool
    '''
    return await db_pool.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE email = $1)", email)

async def get_user_id_by_state_db(db_pool: asyncpg.pool.Pool, state: str) -> Optional[int]:
    '''
    Retrieves user_id from the oauth_state table using a state value.

    This function assumes an `oauth_state` table exists. If the table does not exist,
    an error is logged and None is returned.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param state: The OAuth state value to look up.
    :type state: str
    :returns: The user_id associated with the state if found, otherwise None.
    :rtype: Optional[int]
    :raises asyncpg.exceptions.UndefinedTableError: Internally caught if oauth_state table is missing.
    '''
    # This function assumes an oauth_state table: CREATE TABLE oauth_state (state TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), created_at TIMESTAMPTZ DEFAULT NOW());
    # If this table does not exist, this function will fail.
    # Consider adding a TTL to state entries.
    try:
        user_id = await db_pool.fetchval("SELECT user_id FROM oauth_state WHERE state = $1", state)
        return user_id
    except asyncpg.exceptions.UndefinedTableError:
        logger.error("oauth_state table does not exist. Cannot retrieve user_id by state.")
        return None


async def store_oauth_state_db(db_pool: asyncpg.pool.Pool, state: str, user_id: int) -> None:
    '''
    Stores an OAuth state value with an associated user_id in the oauth_state table.

    Assumes an `oauth_state` table exists. Logs the action or failure if the table is missing.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param state: The OAuth state value to store.
    :type state: str
    :param user_id: The user_id to associate with the state.
    :type user_id: int
    :returns: None
    :rtype: None
    :raises asyncpg.exceptions.UndefinedTableError: Internally caught if oauth_state table is missing.
    '''
    try:
        await db_pool.execute("INSERT INTO oauth_state (state, user_id) VALUES ($1, $2)", state, user_id)
        await log_generic_action_db(
            db_pool,
            username="system_oauth_state_storage",
            event_type="oauth_state_storage",
            data={
                "action_description": f"OAuth state '{state}' stored for user ID {user_id}.",
                "state": state,
                "user_id": user_id
            }
        )
    except asyncpg.exceptions.UndefinedTableError:
        logger.error("oauth_state table does not exist. Cannot store OAuth state.")
        await log_generic_action_db(
            db_pool,
            username="system_oauth_state_storage",
            event_type="oauth_state_storage_failure",
            data={
                "action_description": "Failed to store OAuth state due to missing oauth_state table.",
                "state": state,
                "user_id": user_id
            }
        )
        # Decide if to raise or just log. For now, logging.
    except Exception as e:
        logger.error(f"Error storing oauth state: {e}")


async def delete_oauth_state_db(db_pool: asyncpg.pool.Pool, state: str) -> None:
    '''
    Deletes an OAuth state value from the oauth_state table after it has been used.

    Assumes an `oauth_state` table exists. Logs the action or failure if the table is missing.

    :param db_pool: The database connection pool.
    :type db_pool: asyncpg.pool.Pool
    :param state: The OAuth state value to delete.
    :type state: str
    :returns: None
    :rtype: None
    :raises asyncpg.exceptions.UndefinedTableError: Internally caught if oauth_state table is missing.
    '''
    try:
        await db_pool.execute("DELETE FROM oauth_state WHERE state = $1", state)
        await log_generic_action_db(
            db_pool,
            username="system_oauth_state_deletion",
            event_type="oauth_state_deletion",
            data={
                "action_description": f"OAuth state '{state}' deleted.",
                "state": state
            }
        )
    except asyncpg.exceptions.UndefinedTableError:
        await log_generic_action_db(
            db_pool,
            username="system_oauth_state_deletion",
            event_type="oauth_state_deletion_failure",
            data={
                "action_description": "Failed to delete OAuth state due to missing oauth_state table.",
                "state": state
            }
        )
    except Exception as e:
        logger.error(f"Error deleting oauth state: {e}")