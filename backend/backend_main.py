"""Main FastAPI application for the ad1 platform.

This module defines the FastAPI application, including CORS middleware,
database connection setup (PostgreSQL with asyncpg), background task scheduling,
API endpoints for managing emails, documents, users, audit trails,
scheduler tasks, application settings, and handles OAuth2 authentication flows.
It also integrates with Gmail API for email operations and provides
WebSocket support for real-time agent interactions.
"""
# FastAPI backend for Ornex Mail
# Entry point: main.py
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, Query, Request # Import Request
from fastapi.responses import RedirectResponse # Import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional, Union
import json
from passlib.context import CryptContext
try:
    from asyncpg.exceptions import UniqueViolationError
except ImportError:
    # Fallback for older asyncpg versions or if not specifically needed for all flows
    UniqueViolationError = None
from dotenv import load_dotenv
import os
import logging
import asyncpg
from fastapi import HTTPException
import uuid
import datetime
from fastapi.responses import JSONResponse, Response # Import Response
import base64 # Import base64
from google_auth_oauthlib.flow import Flow
from agent.agent_scheduler import AgentScheduler
from agent.agent_ws import agent_websocket
from agent.email_checker import check_new_emails
from gmail_utils.gmail_auth import generate_auth_url # Keep generate_auth_url
from gmail_utils.gmail_mcp_tools_wrapper import (
    list_emails, get_email, label_email, send_email, draft_email, read_email, search_emails, modify_email, delete_email, list_email_labels, create_label, update_label, delete_label, get_or_create_label, batch_modify_emails, batch_delete_emails
)
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__) # Initialize logger
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mailwhisperer")
app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Email/Audit models
class Email(BaseModel):
    """Represents an email message."""
    id: int
    subject: str
    sender: str
    body: str
    label: Optional[str] = None
    type: Optional[str] = None
    short_description: Optional[str] = None

class AuditTrail(BaseModel):
    """Represents an audit trail log entry."""
    id: int
    email_id: Optional[int] = None # Matches DB schema (can be NULL)
    action: str
    username: str # Matches DB column name "username"
    timestamp: str

class SchedulerTask(BaseModel):
    """Represents a scheduled task or workflow configuration."""
    id: str
    type: str
    description: str
    status: str = "active"
    nextRun: Optional[str] = None
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None
    interval: Optional[int] = None
    condition: Optional[str] = None
    actionDesc: Optional[str] = None
    trigger_type: str
    workflow_config: Optional[dict] = None
    workflow_name: Optional[str] = None

class SchedulerTaskCreate(BaseModel):
    """Data model for creating a new scheduled task."""
    type: str
    description: str
    trigger_type: str
    status: str = "active"
    workflow_name: Optional[str] = None
    workflow_config: Optional[dict] = None
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None
    interval: Optional[int] = None
    condition: Optional[str] = None
    actionDesc: Optional[str] = None

class CreateUserRequest(BaseModel):
    """Data model for creating a new user."""
    email: str
    password: str
    is_admin: bool = False
    roles: list[str] = []
    google_id: Optional[str] = None # Added for Google OAuth

class UpdateUserRequest(BaseModel):
    """Data model for updating an existing user."""
    email: Optional[str] = None # Allow changing email, though be cautious with this
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    roles: Optional[list[str]] = None
    google_id: Optional[str] = None # Added for Google OAuth
    google_access_token: Optional[str] = None # Field for updating access token
    google_refresh_token: Optional[str] = None # Field for updating refresh token


class User(BaseModel):
    """Represents a user in the system."""
    id: int | None = None
    email: str
    password: str | None = None # Password hash, not plaintext
    is_admin: bool = False
    roles: list[str] = []
    google_id: Optional[str] = None
    mcp_token: Optional[str] = None # Added for MCP token
    google_access_token: Optional[str] = None # Ensure this is here
    google_refresh_token: Optional[str] = None # Added for Google refresh token

class ProcessingTask(BaseModel):
    """Represents a task for processing an email or document."""
    id: int # from tasks table
    email_id: int
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    # Fields from emails table
    email_subject: Optional[str] = None
    email_sender: Optional[str] = None
    email_body: Optional[str] = None
    email_received_at: Optional[datetime.datetime] = None
    email_label: Optional[str] = None
    workflow_type: Optional[str] = None
    email_short_description: Optional[str] = None

# New Pydantic models for Settings
class EmailType(BaseModel):
    """Represents a configurable email type/topic for classification."""
    id: Optional[int] = None # ID is optional for creation
    topic: str
    description: Optional[str] = None

class KeyFeature(BaseModel):
    """Represents a configurable key feature for workflow association."""
    id: Optional[int] = None # ID is optional for creation
    name: str

class SettingsData(BaseModel):
    """Data model for application settings."""
    email_grabber_frequency_type: str
    email_grabber_frequency_value: int
    email_types: List[EmailType]
    key_features: List[KeyFeature]

class SetTaskStatusRequest(BaseModel):
    """Data model for setting the status of a task."""
    status: str

# Document model
class Document(BaseModel):
    """Represents a document, typically an email attachment."""
    id: int
    email_id: int
    filename: str
    content_type: str
    data_b64: str # Base64 encoded content
    is_processed: bool
    created_at: datetime.datetime

# DB pool
@app.on_event("startup")
async def startup():
    """Initializes application state on startup.

    Sets up the database connection pool, initializes the agent scheduler,
    schedules the global email checking cron job based on settings,
    and processes ADMIN_EMAILS environment variable to create initial admin users.
    """
    app.state.db = await asyncpg.create_pool(DATABASE_URL)
    app.state.scheduler = AgentScheduler()

    # --- GLOBAL EMAIL CHECKING CRONJOB ---
    # On startup, schedule only ONE global cronjob for check_new_emails
    # Get global frequency from settings
    db_pool = app.state.db
    freq_type_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_type'")
    freq_value_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_value'")
    freq_type = freq_type_row['value'] if freq_type_row and freq_type_row['value'] else 'days'
    freq_value_str = freq_value_row['value'] if freq_value_row and freq_value_row['value'] else '1'
    try:
        freq_value = int(freq_value_str)
        if freq_type == 'days':
            interval_seconds = freq_value * 86400
        elif freq_type == 'minutes':
            interval_seconds = freq_value * 60
        else:
            interval_seconds = 86400
    except Exception:
        interval_seconds = 86400
    # Schedule the global email checking job
    app.state.scheduler.schedule_cron(
        'global_email_cron', check_new_emails, interval_seconds, app.state.db
    )
    print(f"Scheduled global email checking job to run every {interval_seconds} seconds.")

    # Process ADMIN_EMAILS
    admin_emails_str = os.getenv("ADMIN_EMAILS")
    if admin_emails_str:
        admin_emails = [email.strip() for email in admin_emails_str.split(',')]
        default_password = "changeme_admin"  # Consider a more secure approach for production
        hashed_password = pwd_context.hash(default_password)

        for email in admin_emails:
            try:
                user_exists = await app.state.db.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE email = $1)", email)
                if not user_exists:
                    await app.state.db.execute(
                        """
                        INSERT INTO users (email, password, is_admin, roles)
                        VALUES ($1, $2, $3, $4)
                        """,
                        email, hashed_password, True, ["admin"]
                    )
                    logging.info(f"Admin user {email} created with default password.")
                else:
                    logging.info(f"Admin user {email} already exists.")
            except Exception as e:
                logging.error(f"Error processing admin email {email}: {e}")


@app.on_event("shutdown")
async def shutdown():
    """Cleans up application state on shutdown.

    Cancels all scheduled tasks and closes the database connection pool.
    """
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.cancel_all() # Assuming a method to cancel tasks
    await app.state.db.close()

# Email endpoints
@app.get("/api/emails", response_model=List[Email])
async def get_emails():
    """Retrieves a list of all emails.

    Returns:
        List[Email]: A list of email objects.
    """
    rows = await app.state.db.fetch("SELECT id, subject, sender, body, label, type, short_description FROM emails")
    print(rows)
    return [dict(row) for row in rows]

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_email(email_id: int):
    """Retrieves a specific email by its ID.

    Args:
        email_id (int): The ID of the email to retrieve.

    Returns:
        Email: The email object.

    Raises:
        HTTPException: If the email with the given ID is not found.
    """
    row = await app.state.db.fetchrow("SELECT id, subject, sender, body, label, type, short_description FROM emails WHERE id=$1", email_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    print(row)
    return dict(row)

@app.post("/api/emails/{email_id}/label")
async def label_email_endpoint(email_id: int, label: str):
    """Applies a label to a specific email.

    Args:
        email_id (int): The ID of the email to label.
        label (str): The label to apply to the email.

    Returns:
        dict: A status confirmation message.
    """
    await app.state.db.execute("UPDATE emails SET label=$1 WHERE id=$2", label, email_id)
    # Audit log
    # await app.state.db.execute(
    #     "INSERT INTO audit_trail (email_id, action, user, timestamp) VALUES ($1, $2, $3, NOW())",
    #     email_id, f"label:{label}", "user",  # TODO: real user
    # )
    # Using new generic logger
    await log_generic_action(
        db_pool=app.state.db,
        action_description=f"Email ID {email_id} labeled as '{label}'",
        username="user_api", # Placeholder for actual user if available from auth context
        email_id=email_id
    )
    return {"status": "ok"}

@app.get("/api/audit", response_model=List[AuditTrail])
async def get_audit():
    """Retrieves the latest audit trail entries.

    Returns:
        List[AuditTrail]: A list of audit trail objects, ordered by timestamp descending.
    """
    rows = await app.state.db.fetch("SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT 100")
    return [dict(row) for row in rows]

# WebSocket for agent chat (MCP integration)
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    """Handles WebSocket connections for agent interactions.

    Args:
        websocket (WebSocket): The WebSocket connection instance.
    """
    await agent_websocket(websocket)

# Remove global scheduler instance if now managed on app.state
# scheduler = AgentScheduler() # This line can be removed if app.state.scheduler is the sole instance

# In-memory task store for demo (replace with DB in production)
# scheduled_tasks: List[SchedulerTask] = [] # This line is now fully removed

@app.get("/api/scheduler/tasks", response_model=List[SchedulerTask])
async def get_scheduler_tasks(request: Request):
    """Retrieves all configured scheduler tasks (workflows).

    Args:
        request (Request): The FastAPI request object.

    Returns:
        List[SchedulerTask]: A list of scheduler task objects.
    """
    rows = await request.app.state.db.fetch("SELECT id, type, description, status, nextRun, to_email as \"to\", subject, body, date_val as \"date\", interval_seconds as \"interval\", condition, actionDesc, trigger_type, workflow_config, workflow_name FROM scheduler_tasks")
    tasks = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get('workflow_config') is not None:
            try:
                row_dict['workflow_config'] = json.loads(row_dict['workflow_config'])
            except Exception: # Handle potential JSON parsing errors
                logger.error(f"Error parsing workflow_config for task {row_dict.get('id')}: {row_dict.get('workflow_config')}")
                row_dict['workflow_config'] = None
        tasks.append(row_dict)
    return tasks

@app.post("/api/scheduler/task", response_model=SchedulerTask)
async def create_scheduler_task(task_create_data: SchedulerTaskCreate, request: Request):
    """Creates a new scheduler task (workflow).

    Args:
        task_create_data (SchedulerTaskCreate): The data for the new task.
        request (Request): The FastAPI request object.

    Returns:
        SchedulerTask: The created scheduler task object.

    Raises:
        HTTPException: If workflow_config is not serializable or if there's an error during creation.
    """
    import math # Should be at the top of the file
    import traceback # Should be at the top of the file
    try:
        task_id = str(uuid.uuid4())
        if task_create_data.status is None:
            task_create_data.status = "active"

        # Ensure workflow_config is a JSON-serializable string or None
        workflow_config_data = task_create_data.workflow_config
        db_workflow_config = None
        if workflow_config_data is not None:
            if not isinstance(workflow_config_data, dict):
                try: # Attempt to parse if it's a string that looks like a dict
                    workflow_config_data = json.loads(json.dumps(workflow_config_data)) # Normalize
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"workflow_config is not a valid dictionary or serializable: {e}")
            db_workflow_config = json.dumps(workflow_config_data)  # Serialize dict to JSON string for DB

        print(f"Creating scheduler task with DB workflow_config: {db_workflow_config}")
        await request.app.state.db.execute(
            """
            INSERT INTO scheduler_tasks (id, type, description, status, nextRun, to_email, subject, body, date_val, interval_seconds, condition, actionDesc, trigger_type, workflow_config, workflow_name)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            task_id, task_create_data.type, task_create_data.description, task_create_data.status, None, # nextRun is managed by scheduler
            task_create_data.to, task_create_data.subject, task_create_data.body, task_create_data.date, task_create_data.interval,
            task_create_data.condition, task_create_data.actionDesc, task_create_data.trigger_type, db_workflow_config, task_create_data.workflow_name
        )

        # Fetch the created task to return the full SchedulerTask model
        created_task_record = await request.app.state.db.fetchrow(
            "SELECT id, type, description, status, nextRun, to_email as \"to\", subject, body, date_val as \"date\", interval_seconds as \"interval\", condition, actionDesc, trigger_type, workflow_config, workflow_name FROM scheduler_tasks WHERE id = $1",
            task_id
        )
        if not created_task_record:
            raise HTTPException(status_code=500, detail="Failed to retrieve created task.")

        created_task_dict = dict(created_task_record)
        if created_task_dict.get('workflow_config') is not None: # This is now a JSON string from DB
            try:
                created_task_dict['workflow_config'] = json.loads(created_task_dict['workflow_config']) # Deserialize for response
            except Exception:
                logger.error(f"Error parsing workflow_config from DB for task {created_task_dict.get('id')}")
                created_task_dict['workflow_config'] = None
        created_task = SchedulerTask(**created_task_dict)

        # Register cron workflow in scheduler if trigger_type is 'cron' and status is 'active'
        # This part is currently commented out as only one global cron job is active.
        # if created_task.trigger_type == 'cron' and created_task.status == 'active':
            # ... (scheduling logic based on global settings, currently handled by global cron) ...
            # logging.info(f"Scheduled cron workflow '{created_task.workflow_name}' ({created_task.id}) to run every {interval_seconds} seconds based on global settings.")

        await log_generic_action(
            db_pool=request.app.state.db,
            action_description=f"Workflow '{created_task.workflow_name}' (ID: {created_task.id}) of type '{created_task.trigger_type}' created.",
            username="user_api"
        )
        return created_task
    except HTTPException: # Re-raise HTTPExceptions
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Error in create_scheduler_task: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@app.post("/api/scheduler/task/{task_id}/pause")
async def pause_scheduler_task(task_id: str, request: Request):
    """Pauses or resumes a specific scheduler task.

    Args:
        task_id (str): The ID of the task to pause/resume.
        request (Request): The FastAPI request object.

    Returns:
        dict: The new status of the task.

    Raises:
        HTTPException: If the task is not found.
    """
    current_status = await request.app.state.db.fetchval("SELECT status FROM scheduler_tasks WHERE id = $1", task_id)
    if current_status is None:
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = "paused" if current_status == "active" else "active"
    await request.app.state.db.execute(
        "UPDATE scheduler_tasks SET status = $1 WHERE id = $2",
        new_status, task_id
    )
    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Workflow '{task_id}' status changed to '{new_status}'.",
        username="user_api" # Placeholder
    )
    # Note: Actual pausing/resuming of individual cron tasks is currently not done
    # as the system relies on a single global email checking cron.
    # This endpoint primarily updates the task's status in the database.
    return {"status": new_status}

@app.delete("/api/scheduler/task/{task_id}")
async def delete_scheduler_task(task_id: str, request: Request):
    """Deletes a specific scheduler task.

    Args:
        task_id (str): The ID of the task to delete.
        request (Request): The FastAPI request object.

    Returns:
        dict: Confirmation of deletion.

    Raises:
        HTTPException: If the task is not found.
    """
    task_record = await request.app.state.db.fetchrow("SELECT id, trigger_type FROM scheduler_tasks WHERE id = $1", task_id)
    if not task_record:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await request.app.state.db.execute("DELETE FROM scheduler_tasks WHERE id = $1", task_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Task not found during delete operation, though it existed moments before.")

    # Unscheduling logic for individual cron tasks is currently not active.
    # if task_record['trigger_type'] == 'cron':
    #     request.app.state.scheduler.cancel_task(task_id) # Assuming AgentScheduler has such a method
    #     logging.info(f"Cancelled cron task {task_id} in scheduler's internal scheduling (if applicable).")

    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Workflow '{task_id}' deleted.",
        username="user_api" # Placeholder
    )
    return {"ok": True}

# Settings Endpoints
@app.get("/api/settings", response_model=SettingsData)
async def get_settings(request: Request):
    """Retrieves current application settings.

    This includes email grabber frequency, defined email types (topics),
    and key features for workflow association.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        SettingsData: The current application settings.
    """
    db_pool = request.app.state.db

    # Fetch email grabber frequency
    freq_type_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_type'")
    freq_value_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_value'")

    freq_type = freq_type_row['value'] if freq_type_row and freq_type_row['value'] else 'days'
    freq_value = int(freq_value_row['value']) if freq_value_row and freq_value_row['value'] and freq_value_row['value'].isdigit() else 1

    # Fetch email types
    email_types_rows = await db_pool.fetch("SELECT id, topic, description FROM email_types ORDER BY topic")
    email_types_list = [EmailType(**dict(row)) for row in email_types_rows]

    # Fetch key features
    key_features_rows = await db_pool.fetch("SELECT id, name FROM key_features ORDER BY name")
    key_features_list = [KeyFeature(**dict(row)) for row in key_features_rows]

    return SettingsData(
        email_grabber_frequency_type=freq_type,
        email_grabber_frequency_value=freq_value,
        email_types=email_types_list,
        key_features=key_features_list
    )

@app.post("/api/settings")
async def save_settings(settings_data: SettingsData, request: Request):
    """Saves application settings.

    Updates email grabber frequency, email types (topics), and key features.
    This operation is performed within a database transaction.

    Args:
        settings_data (SettingsData): The new settings to save.
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.
    """
    db_pool = request.app.state.db

    async with db_pool.acquire() as connection:
        async with connection.transaction():
            # Save email grabber frequency
            await connection.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                'email_grabber_frequency_type', settings_data.email_grabber_frequency_type
            )
            await connection.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                'email_grabber_frequency_value', str(settings_data.email_grabber_frequency_value)
            )

            # Save email types (clear existing and insert new)
            await connection.execute("DELETE FROM email_types")
            if settings_data.email_types:
                email_type_values = [(et.topic, et.description) for et in settings_data.email_types]
                await connection.copy_records_to_table('email_types', records=email_type_values, columns=['topic', 'description'])

            # Save key features (clear existing and insert new)
            await connection.execute("DELETE FROM key_features")
            if settings_data.key_features:
                key_feature_values = [(kf.name,) for kf in settings_data.key_features]
                await connection.copy_records_to_table('key_features', records=key_feature_values, columns=['name'])

    await log_generic_action(
        db_pool=db_pool,
        action_description="Settings updated (Email Grabber Frequency, Email Types, Key Features)",
        username="user_api" # Placeholder
    )

    return {"status": "success", "message": "Settings saved successfully"}

# Note: Individual CRUD endpoints for EmailTypes and KeyFeatures were considered
# but are currently handled via the main /api/settings endpoint for simplicity.
# If more granular control is needed in the future, these can be uncommented and implemented.

# User Management Endpoints
@app.post("/api/users/add", response_model=User)
async def addUser(user_create_request: CreateUserRequest):
    """Creates a new user in the system.

    Args:
        user_create_request (CreateUserRequest): The details of the user to create.

    Returns:
        User: The created user object (excluding password).

    Raises:
        HTTPException: If a user with the same email already exists or if there's an unexpected error.
    """
    hashed_password = pwd_context.hash(user_create_request.password)
    try:
        query = """
            INSERT INTO users (email, password, is_admin, roles, google_id, google_access_token, google_refresh_token)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, email, is_admin, roles, google_id, mcp_token, google_access_token, google_refresh_token
        """ # Added mcp_token and tokens to RETURNING for completeness
        row = await app.state.db.fetchrow(
            query,
            user_create_request.email,
            hashed_password,
            user_create_request.is_admin,
            user_create_request.roles,
            user_create_request.google_id,
            None,  # google_access_token initialized as None
            None   # google_refresh_token initialized as None
        )
        if row:
            # Ensure all fields required by User model are present, even if None
            user_data = dict(row)
            user_data.setdefault('mcp_token', None)
            user_data.setdefault('google_access_token', None)
            user_data.setdefault('google_refresh_token', None)
            created_user = User(**user_data)

            await log_generic_action(
                db_pool=app.state.db,
                action_description=f"User '{created_user.email}' created. Admin: {created_user.is_admin}, Roles: {created_user.roles}",
                username="admin_api" # Placeholder, ideally from auth context
            )
            return created_user
        else:
            raise HTTPException(status_code=500, detail="Failed to create user due to an unexpected database error.")
    except UniqueViolationError:
        raise HTTPException(status_code=400, detail=f"User with email {user_create_request.email} already exists.")
    except Exception as e:
        logging.error(f"Error creating user {user_create_request.email}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while creating the user.")

@app.put("/api/users/{user_identifier}/set", response_model=User)
async def setUser(user_identifier: Union[int, str], user_update_request: UpdateUserRequest):
    """Updates an existing user's details.

    The user can be identified by their ID or email address.

    Args:
        user_identifier (Union[int, str]): The ID or email of the user to update.
        user_update_request (UpdateUserRequest): The user details to update.

    Returns:
        User: The updated user object.

    Raises:
        HTTPException: If the user is not found, if the new email already exists,
                       or if there's an unexpected error.
    """
    # Determine if identifier is email or ID
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier) # Ensure it's an int if it's a numeric string
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format. Must be an integer or numeric string.")
    else:
        raise HTTPException(status_code=400, detail="Invalid user identifier. Must be an email string or an integer ID.")

    # Fetch existing user data including all relevant fields for User model
    existing_user_row = await app.state.db.fetchrow(
        f"SELECT id, email, password, is_admin, roles, google_id, mcp_token, google_access_token, google_refresh_token FROM users WHERE {condition_column} = $1",
        user_identifier
    )
    if not existing_user_row:
        raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found.")

    existing_user_data = dict(existing_user_row)

    update_fields = user_update_request.model_dump(exclude_unset=True) # Get only provided fields

    if "password" in update_fields and update_fields["password"] is not None:
        update_fields["password"] = pwd_context.hash(update_fields["password"])
    elif "password" in update_fields and update_fields["password"] is None: # Explicitly setting password to None is not typical
        del update_fields["password"] # Or handle as an error

    if not update_fields:
        # Return existing user data if no changes are requested, ensuring all fields for User model
        return User(**existing_user_data)

    # Construct SET clauses dynamically
    set_parts = []
    values = [user_identifier] # Start with the identifier for the WHERE clause
    for i, (key, value) in enumerate(update_fields.items()):
        set_parts.append(f"{key} = ${i+2}") # Parameters are $1, $2, $3, ...
        values.append(value)

    set_clauses = ", ".join(set_parts)

    # Ensure RETURNING clause includes all fields for the User model
    returning_fields = "id, email, is_admin, roles, google_id, mcp_token, google_access_token, google_refresh_token"
    query = f"UPDATE users SET {set_clauses} WHERE {condition_column} = $1 RETURNING {returning_fields}"

    try:
        updated_user_row = await app.state.db.fetchrow(query, *values)
        if updated_user_row:
            # Ensure all fields for User model are present, even if None
            updated_user_data = dict(updated_user_row)
            updated_user_data.setdefault('mcp_token', None) # Ensure defaults if not returned or None
            updated_user_data.setdefault('google_access_token', None)
            updated_user_data.setdefault('google_refresh_token', None)
            updated_user = User(**updated_user_data)

            # Create a dictionary of actual changes for logging
            changes_logged = {k: v for k, v in update_fields.items() if k != "password"} # Don't log password hash
            if "password" in update_fields:
                changes_logged["password"] = "updated"

            await log_generic_action(
                db_pool=app.state.db,
                action_description=f"User '{existing_user_data['email']}' (ID: {existing_user_data['id']}) updated. Changes: {json.dumps(changes_logged)}",
                username="admin_api" # Placeholder
            )
            return updated_user
        else:
            # This should not happen if the user was found initially and the query is correct
            raise HTTPException(status_code=500, detail="Failed to update user due to an unexpected database error.")
    except UniqueViolationError: # Handle email collision if email is being changed
        raise HTTPException(status_code=400, detail=f"Another user with email {user_update_request.email} already exists.")
    except Exception as e:
        logging.error(f"Error updating user {user_identifier}: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while updating the user: {str(e)}")

@app.delete("/api/users/{user_identifier}")
async def deleteUser(user_identifier: Union[int, str]):
    """Deletes a user from the system.

    The user can be identified by their ID or email address.

    Args:
        user_identifier (Union[int, str]): The ID or email of the user to delete.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the user is not found or if there's an unexpected error.
    """
    # Determine if identifier is email or ID
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format. Must be an integer or numeric string.")
    else:
        raise HTTPException(status_code=400, detail="Invalid user identifier. Must be an email string or an integer ID.")

    user_to_delete_row = await app.state.db.fetchrow(
        f"SELECT id, email FROM users WHERE {condition_column} = $1",
        user_identifier
    )
    if not user_to_delete_row:
        raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found.")

    user_email_for_log = user_to_delete_row['email']
    user_id_for_log = user_to_delete_row['id']

    try:
        result = await app.state.db.execute(
            f"DELETE FROM users WHERE {condition_column} = $1",
            user_identifier
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found during delete, though existed moments before.")

        await log_generic_action(
            db_pool=app.state.db,
            action_description=f"User '{user_email_for_log}' (ID: {user_id_for_log}) deleted.",
            username="admin_api" # Placeholder
        )
        return {"status": "success", "message": f"User with {condition_column} '{user_identifier}' deleted successfully."}
    except Exception as e:
        logging.error(f"Error deleting user {user_identifier}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while deleting the user.")

@app.get("/api/users", response_model=List[User])
async def list_users():
    """Lists all users in the system.

    Returns:
        List[User]: A list of user objects (excluding passwords).
    """
    # Ensure all fields for User model are selected, providing defaults for optional ones if necessary
    rows = await app.state.db.fetch("SELECT id, email, is_admin, roles, google_id, mcp_token, google_access_token, google_refresh_token FROM users")
    users = []
    for row in rows:
        user_data = dict(row)
        # Ensure defaults for optional fields if they might be missing from a SELECT * or specific SELECT
        user_data.setdefault('password', None) # Password hash not sent
        user_data.setdefault('mcp_token', None)
        user_data.setdefault('google_access_token', None)
        user_data.setdefault('google_refresh_token', None)
        users.append(User(**user_data))
    return users


@app.get("/oauth2callback")
async def oauth2callback(request: Request, code: str = Query(...), state: str = Query(None)):
    """Handles the OAuth2 callback from Google.

    Exchanges the authorization code for access and refresh tokens,
    and stores these tokens in the database for the user identified by the state parameter.

    Args:
        request (Request): The FastAPI request object.
        code (str): The authorization code provided by Google.
        state (str, optional): The state parameter, expected to contain user ID.

    Returns:
        RedirectResponse: Redirects the user to a frontend page indicating success or failure.
    """
    logger.info("-----------------------------------------")
    logger.info(f"Received OAuth2 callback with code: {code}, state: {state}")

    user_id = None
    if state and '-' in state: # Assuming state format is "some_original_state-user_id"
        try:
            user_id_str = state.split('-')[-1]
            user_id = int(user_id_str)
            logger.info(f"Extracted user ID from state: {user_id}")
        except ValueError:
            logger.error(f"Could not parse user ID from state part: '{user_id_str}' in state: '{state}'")
            return RedirectResponse(url="http://localhost:5173/settings?auth=failure_invalid_state")
    else:
         logger.error(f"State parameter missing user ID or in unexpected format: {state}")
         return RedirectResponse(url="http://localhost:5173/settings?auth=failure_missing_state")

    # Ensure client secrets file path is correct relative to the execution directory
    client_secrets_path = os.path.join(os.path.dirname(__file__), 'auth/gcp-oauth.keys.json')
    if not os.path.exists(client_secrets_path):
        logger.error(f"OAuth client secrets file not found at: {client_secrets_path}")
        raise HTTPException(status_code=500, detail="OAuth client configuration error.")

    flow = Flow.from_client_secrets_file(
        client_secrets_path,
        scopes=['https://mail.google.com/'], # Ensure scopes match what was requested
        redirect_uri='http://localhost:8001/oauth2callback') # Must match one in GCP console

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        access_token = credentials.token
        refresh_token = credentials.refresh_token # Might be None if already granted or not requested properly

        logger.info(f"Obtained access token for user ID {user_id}. Refresh token available: {refresh_token is not None}")

        # Save tokens to the database
        db_pool = request.app.state.db
        await db_pool.execute(
            "UPDATE users SET google_access_token = $1, google_refresh_token = COALESCE($2, google_refresh_token) WHERE id = $3",
            access_token, refresh_token, user_id # COALESCE keeps existing refresh token if new one is None
        )
        logger.info(f"Successfully stored Gmail credentials for user ID: {user_id}")
        return RedirectResponse(url="http://localhost:5173/settings?auth=success")

    except Exception as e:
        logger.error(f"Error during OAuth token exchange or DB update for user ID {user_id}: {e}")
        # Consider more specific error logging or handling here
        return RedirectResponse(url="http://localhost:5173/settings?auth=failure_token_exchange")

@app.get("/api/oauth-config")
def get_oauth_config():
    """Retrieves the Google OAuth client configuration.

    This is used by the frontend to initialize the Google Login flow.

    Returns:
        JSONResponse: The OAuth client configuration from `auth/gcp-oauth.keys.json`.
                      Returns 404 if file not found, 500 on other errors.
    """
    # Ensure the path is relative to this file's location (backend_main.py)
    config_path = os.path.join(os.path.dirname(__file__), 'auth/gcp-oauth.keys.json')
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except FileNotFoundError:
        logger.error(f"Google OAuth config file not found at: {config_path}")
        return JSONResponse(status_code=404, content={"error": "Google OAuth client configuration file not found."})
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from Google OAuth config file: {config_path}")
        return JSONResponse(status_code=500, content={"error": "Error reading Google OAuth configuration."})
    except Exception as e:
        logger.error(f"Unexpected error reading Google OAuth config: {e}")
        return JSONResponse(status_code=500, content={"error": "An unexpected error occurred."})

@app.post("/api/userinfo")
async def userinfo(request: Request):
    """Retrieves user information (admin status, roles, Google ID) based on email.

    Args:
        request (Request): The FastAPI request object containing user email in JSON body.

    Returns:
        dict: User information including `is_admin`, `roles`, and `google_id`.
              Returns default values if user not found.

    Raises:
        HTTPException: If email is missing in the request.
    """
    data = await request.json()
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required in the request body.")

    row = await app.state.db.fetchrow("SELECT is_admin, roles, google_id FROM users WHERE email=$1", email)
    logger.info(f"Userinfo query for email: {email} returned row: {row}")
    if not row:
        # Return a default structure if user not found, to prevent frontend errors
        return {"is_admin": False, "roles": [], "google_id": None}
    return {"is_admin": row["is_admin"], "roles": row["roles"], "google_id": row["google_id"]}


@app.get("/api/processing_tasks", response_model=List[ProcessingTask])
async def get_processing_tasks(request: Request):
    """Retrieves a list of all processing tasks.

    Tasks are joined with email details and ordered by creation date.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        List[ProcessingTask]: A list of processing task objects.
    """
    query = """
    SELECT
        t.id,
        t.email_id,
        t.status,
        t.created_at,
        t.updated_at,
        e.subject AS email_subject,
        e.sender AS email_sender,
        e.body AS email_body,        -- Consider if full body is needed here or if it's too large
        e.received_at AS email_received_at,
        e.label AS email_label,
        e.short_description AS email_short_description,
        t.workflow_type
    FROM tasks t
    LEFT JOIN emails e ON t.email_id = e.id
    ORDER BY t.created_at DESC;
    """
    rows = await request.app.state.db.fetch(query)
    # Ensure all fields for ProcessingTask are present, providing defaults if necessary
    tasks_data = []
    for row_proxy in rows:
        row_dict = dict(row_proxy)
        # Ensure all model fields are present, example for potentially missing ones from a minimal task entry
        row_dict.setdefault('email_subject', None)
        row_dict.setdefault('email_sender', None)
        row_dict.setdefault('email_body', None) # Or handle large bodies appropriately
        row_dict.setdefault('email_received_at', None)
        row_dict.setdefault('email_label', None)
        row_dict.setdefault('email_short_description', None)
        row_dict.setdefault('workflow_type', None) # workflow_type is already in SELECT
        tasks_data.append(ProcessingTask(**row_dict))
    return tasks_data

# Generic Audit Logging Function
async def log_generic_action(db_pool, action_description: str, username: str = "system_event", email_id: Optional[int] = None):
    """Logs a generic action to the audit_trail table.

    Args:
        db_pool: The database connection pool.
        action_description (str): A description of the action performed.
        username (str, optional): The username performing the action. Defaults to "system_event".
        email_id (Optional[int], optional): The ID of the email related to the action, if any. Defaults to None.
    """
    try:
        await db_pool.execute(
            "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
            email_id, action_description, username
        )
    except Exception as e:
        logging.error(f"Failed to log generic action '{action_description}' for user '{username}', email_id '{email_id}': {e}")


async def log_task_action(db_pool, task_id: int, action: str, user: str = "system_user"):
    """Logs a task-specific action to the audit_trail table.

    Enriches the log message with details from the task itself, like status and workflow type.

    Args:
        db_pool: The database connection pool.
        task_id (int): The ID of the task related to the action.
        action (str): The specific action performed on the task (e.g., "Task validated").
        user (str, optional): The username performing the action. Defaults to "system_user".
    """
    db_email_id = None
    task_status = None
    workflow_type = None
    try:
        task_details_record = await db_pool.fetchrow("SELECT email_id, status, workflow_type FROM tasks WHERE id = $1", task_id)
        if task_details_record:
            db_email_id = task_details_record['email_id']
            task_status = task_details_record['status']
            workflow_type = task_details_record['workflow_type']

        action_details_string = f"{action} (Task ID: {task_id}, Current Status: {task_status}, Workflow: {workflow_type or 'N/A'})"

        await db_pool.execute(
            "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
            db_email_id, action_details_string, user
        )
    except Exception as e:
        logging.error(f"Failed to log task action '{action}' for task {task_id}, user '{user}': {e}")


@app.post("/api/processing_tasks/{task_id}/validate")
async def validate_task(task_id: int, request: Request):
    """Marks a specific processing task as 'validated'.

    Args:
        task_id (int): The ID of the task to validate.
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the task with the given ID is not found.
    """
    result = await request.app.state.db.execute(
        "UPDATE tasks SET status = 'validated' WHERE id = $1",
        task_id
    )
    if result == "UPDATE 0": # Check if any row was updated
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or not updated.")

    await log_task_action(request.app.state.db, task_id, action="Task validated. Status changed to 'validated'", user="user_api") # Placeholder user
    return {"status": "success", "message": f"Task {task_id} marked as validated."}

@app.post("/api/processing_tasks/{task_id}/abort")
async def abort_task(task_id: int, request: Request):
    """Marks a specific processing task as 'aborted'.

    Args:
        task_id (int): The ID of the task to abort.
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the task with the given ID is not found.
    """
    result = await request.app.state.db.execute(
        "UPDATE tasks SET status = 'aborted' WHERE id = $1",
        task_id
    )
    if result == "UPDATE 0": # Check if any row was updated
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or not updated.")

    await log_task_action(request.app.state.db, task_id, action="Task aborted. Status changed to 'aborted'", user="user_api") # Placeholder user
    return {"status": "success", "message": f"Task {task_id} marked as aborted."}


@app.post("/api/tasks/{task_id}/status")
async def set_task_status(task_id: int, status_request: SetTaskStatusRequest, request: Request):
    """Manually sets the status of a specific task.

    Args:
        task_id (int): The ID of the task to update.
        status_request (SetTaskStatusRequest): The new status for the task.
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the task with the given ID is not found.
    """
    result = await request.app.state.db.execute(
        "UPDATE tasks SET status = $1 WHERE id = $2",
        status_request.status, task_id
    )
    if result == "UPDATE 0": # Check if any row was updated
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or not updated.")

    await log_task_action(request.app.state.db, task_id, action=f"Task status manually set to '{status_request.status}'", user="user_api") # Placeholder

    return {"status": "success", "message": f"Task {task_id} status updated to {status_request.status}."}

@app.put("/api/scheduler/task/{task_id}", response_model=SchedulerTask)
async def update_scheduler_task(task_id: str, task_update_data: SchedulerTaskCreate, request: Request):
    """Updates an existing scheduler task (workflow).

    Args:
        task_id (str): The ID of the scheduler task to update.
        task_update_data (SchedulerTaskCreate): The new data for the task.
        request (Request): The FastAPI request object.

    Returns:
        SchedulerTask: The updated scheduler task object.

    Raises:
        HTTPException: If the task is not found or if workflow_config is not serializable.
    """
    import traceback # Should be at top of file
    try:
        db_workflow_config = None
        if task_update_data.workflow_config is not None:
            if not isinstance(task_update_data.workflow_config, dict):
                try:
                    workflow_config_dict = json.loads(json.dumps(task_update_data.workflow_config))
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"workflow_config is not a valid dictionary or serializable: {e}")
            else:
                workflow_config_dict = task_update_data.workflow_config
            db_workflow_config = json.dumps(workflow_config_dict)

        result = await request.app.state.db.execute(
            """
            UPDATE scheduler_tasks SET
                type = $1, description = $2, status = $3, to_email = $4, subject = $5, body = $6,
                date_val = $7, interval_seconds = $8, condition = $9, actionDesc = $10,
                trigger_type = $11, workflow_config = $12, workflow_name = $13
            WHERE id = $14
            """,
            task_update_data.type, task_update_data.description, task_update_data.status,
            task_update_data.to, task_update_data.subject, task_update_data.body,
            task_update_data.date, task_update_data.interval, task_update_data.condition,
            task_update_data.actionDesc, task_update_data.trigger_type, db_workflow_config,
            task_update_data.workflow_name, task_id
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Scheduler task not found or not updated.")

        updated_task_record = await request.app.state.db.fetchrow(
            "SELECT id, type, description, status, nextRun, to_email as \"to\", subject, body, date_val as \"date\", interval_seconds as \"interval\", condition, actionDesc, trigger_type, workflow_config, workflow_name FROM scheduler_tasks WHERE id = $1",
            task_id
        )
        if not updated_task_record: # Should not happen if update was successful
             raise HTTPException(status_code=500, detail="Failed to retrieve updated task.")

        updated_task_dict = dict(updated_task_record)
        if updated_task_dict.get('workflow_config') is not None: # String from DB
            try:
                updated_task_dict['workflow_config'] = json.loads(updated_task_dict['workflow_config']) # Deserialize for response
            except Exception:
                logger.error(f"Error parsing workflow_config from DB for updated task {updated_task_dict.get('id')}")
                updated_task_dict['workflow_config'] = None

        await log_generic_action(
            db_pool=request.app.state.db,
            action_description=f"Workflow '{task_id}' updated.",
            username="user_api" # Placeholder
        )
        return SchedulerTask(**updated_task_dict)
    except HTTPException: # Re-raise HTTPExceptions
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Error in update_scheduler_task: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.post("/api/users/{email}/token")
async def save_user_token(email: str, data: dict, request: Request):
    """Saves or updates a user's Google access token.

    Note: This endpoint might be for specific token updates, distinct from the main OAuth flow.
          Consider security implications of updating tokens this way.

    Args:
        email (str): The email of the user whose token is to be saved.
        data (dict): A dictionary containing the "token".
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the token is missing in the request data.
    """
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required in the request data.")

    # Check if user exists
    user_exists = await request.app.state.db.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE email=$1)", email)
    if not user_exists:
        raise HTTPException(status_code=404, detail=f"User with email {email} not found.")

    await request.app.state.db.execute(
        "UPDATE users SET google_access_token=$1 WHERE email=$2", token, email
    )
    await log_generic_action(db_pool=request.app.state.db, action_description=f"Google access token updated for user {email}.", username="user_api_token_update")
    return {"status": "ok"}

@app.get("/api/gmail/auth-url")
async def get_gmail_auth_url(request: Request): # request argument might not be needed if user_id is hardcoded/mocked
    """Generates the Gmail OAuth authorization URL.

    The generated URL includes a state parameter with an appended user ID (currently placeholder).
    This URL is intended for the frontend to initiate the Google OAuth flow.

    Args:
        request (Request): The FastAPI request object (currently unused for user_id).

    Returns:
        dict: A dictionary containing the "auth_url".
    """
    logger.info("Generating Gmail OAuth authorization URL...")
    # Placeholder for actual user ID retrieval from authenticated request context
    user_id = 1 # Example: Replace with actual authenticated user's ID

    auth_url, original_state = generate_auth_url() # Assumes generate_auth_url returns (url, state_value)

    # Append user_id to the state for tracking during callback
    # In production, consider signing or encrypting the state to prevent tampering
    state_with_user_id = f"{original_state}-{user_id}"

    # Replace the original state in the URL with the new state containing user_id
    # This assumes generate_auth_url includes state in a query param like 'state=ORIGINAL_STATE'
    final_auth_url = auth_url.replace(f"state={original_state}", f"state={state_with_user_id}")

    logger.info(f"Generated auth URL with user-specific state: {final_auth_url}")
    return {"auth_url": final_auth_url}

# Add endpoint to get MCP auth URL
@app.get("/api/mcp/auth-url")
async def get_mcp_auth_url():
    """Provides the frontend with the URL to initiate MCP server login (placeholder).

    Returns:
        dict: A dictionary containing the "auth_url".
    """
    # This is a placeholder. The actual URL should come from configuration
    # or be dynamically constructed based on the MCP server's requirements.
    # It typically includes a redirect_uri for the MCP server to call back to.
    mcp_server_base_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000") # Example
    frontend_mcp_callback_url = "http://localhost:8001/mcpcallback" # This app's callback

    # Example: MCP server might have an endpoint like /mcp/authorize
    # This will vary greatly based on the MCP server's implementation.
    mcp_login_url = f"{mcp_server_base_url}/mcp/authorize?client_id=ad1_backend&redirect_uri={frontend_mcp_callback_url}&response_type=token"

    logger.info(f"Generated MCP Auth URL: {mcp_login_url}")
    return {"auth_url": mcp_login_url}

# Add endpoint to handle MCP callback and save token
@app.get("/mcpcallback")
async def mcp_callback(token: str = Query(...), user_email: str = Query(...)): # Added request for db access
    """Handles the callback from the MCP server after successful authentication.

    Receives an MCP token and associates it with the specified user.

    Args:
        token (str): The token provided by the MCP server.
        user_email (str): The email of the user to associate the token with.

    Returns:
        RedirectResponse: Redirects the user to a frontend settings page
                          indicating success or failure of the MCP token association.
    """
    logger.info(f"Received MCP callback for user: {user_email} with a token.")

    user_row = await app.state.db.fetchrow("SELECT id FROM users WHERE email = $1", user_email)

    if user_row:
        await app.state.db.execute(
            "UPDATE users SET mcp_token = $1 WHERE id = $2",
            token, user_row['id']
        )
        logger.info(f"MCP token saved successfully for user: {user_email}")
        await log_generic_action(db_pool=app.state.db, action_description=f"MCP token associated for user {user_email}.", username=user_email)
        return RedirectResponse(url="http://localhost:5173/settings?mcpauth=success") # Adjust frontend URL as needed
    else:
        logger.error(f"User not found for MCP callback: {user_email}")
        return RedirectResponse(url="http://localhost:5173/settings?mcpauth=failure_user_not_found")

# --- AgentScheduler Control Endpoints ---
from fastapi import status as fastapi_status # Already imported, ensure it's used consistently

@app.post("/api/scheduler/start")
async def start_scheduler():
    """Starts the background agent scheduler.

    Returns:
        dict: Status of the scheduler ("running" or error).

    Raises:
        HTTPException: If the scheduler is not available.
    """
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        app.state.scheduler.start() # Assuming start method exists and is synchronous or handled by scheduler
        logger.info("Agent scheduler started via API request.")
        await log_generic_action(db_pool=app.state.db, action_description="Agent scheduler started.", username="system_api")
        return {"status": "running"}
    logger.error("Attempted to start scheduler, but scheduler not found in app.state.")
    raise HTTPException(status_code=500, detail="Scheduler not available or not initialized.")

@app.post("/api/scheduler/stop")
async def stop_scheduler():
    """Stops the background agent scheduler and cancels all its tasks.

    Returns:
        dict: Status of the scheduler ("stopped" or error).

    Raises:
        HTTPException: If the scheduler is not available.
    """
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        app.state.scheduler.cancel_all() # Assuming this stops and cancels tasks
        logger.info("Agent scheduler stopped and tasks cancelled via API request.")
        await log_generic_action(db_pool=app.state.db, action_description="Agent scheduler stopped and tasks cancelled.", username="system_api")
        return {"status": "stopped"}
    logger.error("Attempted to stop scheduler, but scheduler not found in app.state.")
    raise HTTPException(status_code=500, detail="Scheduler not available or not initialized.")

@app.get("/api/scheduler/status")
async def scheduler_status():
    """Gets the current status of the background agent scheduler.

    Returns:
        dict: Current status ("running", "stopped", "unknown", or error).

    Raises:
        HTTPException: If the scheduler is not available.
    """
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        # Assuming AgentScheduler has an is_running() method
        is_running = app.state.scheduler.is_running() if hasattr(app.state.scheduler, 'is_running') else None

        if is_running is True:
            status_str = "running"
        elif is_running is False:
            status_str = "stopped"
        else:
            # is_running might be None if the method doesn't exist or can't determine
            status_str = "unknown"
        logger.debug(f"Scheduler status requested: {status_str}")
        return {"status": status_str}
    logger.error("Attempted to get scheduler status, but scheduler not found in app.state.")
    raise HTTPException(status_code=500, detail="Scheduler not available or not initialized.")

# --- Endpoint to check if Google refresh token is set for a user ---
@app.get("/api/users/{user_identifier}/has_google_refresh_token")
async def has_google_refresh_token(user_identifier: Union[int, str]):
    """Checks if a Google refresh token is set for the specified user.

    Args:
        user_identifier (Union[int, str]): The ID or email of the user to check.

    Returns:
        dict: {"has_refresh_token": True} if token exists and is not empty/null.

    Raises:
        HTTPException: If user not found, or if token is not set (HTTP_400_BAD_REQUEST specifically).
    """
    # Determine if identifier is email or ID
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format. Must be an integer or numeric string.")
    else:
        raise HTTPException(status_code=400, detail="Invalid user identifier. Must be an email string or an integer ID.")

    row = await app.state.db.fetchrow(f"SELECT google_refresh_token FROM users WHERE {condition_column} = $1", user_identifier)
    if not row:
        raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found.")

    refresh_token = row["google_refresh_token"]
    if not refresh_token or refresh_token.strip() == "" or refresh_token.lower() == "none": # More robust check
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=f"Google refresh token not set for user {user_identifier}.")

    return {"has_refresh_token": True}

@app.delete("/api/emails/{email_id}")
async def delete_email_endpoint(email_id: int, request: Request): # Renamed to avoid conflict if 'delete_email' from gmail_utils is imported
    """Deletes an email by its ID from the database.

    Args:
        email_id (int): The ID of the email to delete.
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the email is not found.
    """
    existing_email = await request.app.state.db.fetchrow("SELECT id FROM emails WHERE id = $1", email_id)
    if not existing_email:
        raise HTTPException(status_code=404, detail=f"Email with id {email_id} not found.")

    result = await request.app.state.db.execute("DELETE FROM emails WHERE id = $1", email_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail=f"Email with id {email_id} not found during delete, though existed moments before.")

    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Email ID {email_id} deleted from database.",
        username="user_api", # Placeholder
        email_id=email_id
    )
    return {"status": "ok", "message": f"Email {email_id} deleted successfully from database."}

@app.delete("/api/documents/{document_id}")
async def delete_document_endpoint(document_id: int, request: Request): # Renamed to avoid conflict
    """Deletes a document by its ID from the database.

    Args:
        document_id (int): The ID of the document to delete.
        request (Request): The FastAPI request object.

    Returns:
        dict: A status confirmation message.

    Raises:
        HTTPException: If the document is not found.
    """
    existing_document = await request.app.state.db.fetchrow("SELECT id FROM documents WHERE id = $1", document_id)
    if not existing_document:
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found.")

    result = await request.app.state.db.execute("DELETE FROM documents WHERE id = $1", document_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found during delete, though existed moments before.")

    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Document ID {document_id} deleted from database.",
        username="user_api" # Placeholder
    )
    return {"status": "ok", "message": f"Document {document_id} deleted successfully from database."}

@app.get("/api/documents", response_model=List[Document])
async def get_documents(request: Request):
    """Lists all documents stored in the database.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        List[Document]: A list of document objects.
    """
    rows = await request.app.state.db.fetch("SELECT id, email_id, filename, content_type, data_b64, is_processed, created_at FROM documents ORDER BY created_at DESC")
    return [Document(**dict(row)) for row in rows] # Use model directly for validation

@app.get("/api/documents/{document_id}/content")
async def get_document_content(document_id: int, request: Request):
    """Fetches and returns the content of a specific document.

    The document content is base64 decoded and returned with the appropriate
    content type.

    Args:
        document_id (int): The ID of the document to retrieve content for.
        request (Request): The FastAPI request object.

    Returns:
        Response: The document content with the correct media type.

    Raises:
        HTTPException: If the document is not found or if there's an error decoding content.
    """
    row = await request.app.state.db.fetchrow("SELECT data_b64, content_type, filename FROM documents WHERE id = $1", document_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found")

    # Decode base64 content
    try:
        content_bytes = base64.b64decode(row['data_b64'])
    except Exception as e:
        logger.error(f"Error decoding base64 for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Error decoding document content")

    # Return content with appropriate media type
    # Correcting the f-string syntax for the filename
    return Response(content=content_bytes, media_type=row['content_type'], headers={'Content-Disposition': 'inline; filename="{}"'.format(row['filename'])})
