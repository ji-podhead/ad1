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
from agent_ws import agent_websocket
from fastapi import HTTPException
import uuid
import datetime
from fastapi.responses import JSONResponse, Response # Import Response
import base64 # Import base64
from google_auth_oauthlib.flow import Flow
from backend.agent.agent_scheduler import AgentScheduler, check_new_emails # Import check_new_emails
from backend.gmail.gmail_auth import generate_auth_url # Keep generate_auth_url
from backend.gmail.gmail_mcp_tools_wrapper import (
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
    id: int
    subject: str
    sender: str
    body: str
    label: Optional[str]
    type: Optional[str] = None
    short_description: Optional[str] = None

class AuditTrail(BaseModel):
    id: int
    email_id: Optional[int] = None # Matches DB schema (can be NULL)
    action: str
    username: str # Matches DB column name "username"
    timestamp: str

class SchedulerTask(BaseModel):
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
    email: str
    password: str
    is_admin: bool = False
    roles: list[str] = []
    google_id: Optional[str] = None # Added for Google OAuth

class UpdateUserRequest(BaseModel):
    email: Optional[str] = None # Allow changing email, though be cautious with this
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    roles: Optional[list[str]] = None
    google_id: Optional[str] = None # Added for Google OAuth

class User(BaseModel):
    id: int | None = None
    email: str
    password: str | None = None
    is_admin: bool = False
    roles: list[str] = []
    google_id: Optional[str] = None
    mcp_token: Optional[str] = None # Added for MCP token
    google_access_token: Optional[str] = None # Ensure this is here
    google_refresh_token: Optional[str] = None # Added for Google refresh token

class ProcessingTask(BaseModel):
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
    id: Optional[int] = None # ID is optional for creation
    topic: str
    description: Optional[str] = None

class KeyFeature(BaseModel):
    id: Optional[int] = None # ID is optional for creation
    name: str

class SettingsData(BaseModel):
    email_grabber_frequency_type: str
    email_grabber_frequency_value: int
    email_types: List[EmailType]
    key_features: List[KeyFeature]

class SetTaskStatusRequest(BaseModel):
    status: str

# Document model
class Document(BaseModel):
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
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.cancel_all() # Assuming a method to cancel tasks
    await app.state.db.close()

# Email endpoints
@app.get("/api/emails", response_model=List[Email])
async def get_emails():
    rows = await app.state.db.fetch("SELECT id, subject, sender, body, label, type, short_description FROM emails")
    print(rows)
    return [dict(row) for row in rows]

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_email(email_id: int):
    row = await app.state.db.fetchrow("SELECT id, subject, sender, body, label, type, short_description FROM emails WHERE id=$1", email_id)
    print(row)
    return dict(row)

@app.post("/api/emails/{email_id}/label")
async def label_email(email_id: int, label: str):
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
    rows = await app.state.db.fetch("SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT 100")
    return [dict(row) for row in rows]

# WebSocket for agent chat (MCP integration)
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    await agent_websocket(websocket)

# Remove global scheduler instance if now managed on app.state
# scheduler = AgentScheduler() # This line can be removed if app.state.scheduler is the sole instance

# In-memory task store for demo (replace with DB in production)
# scheduled_tasks: List[SchedulerTask] = [] # This line is now fully removed

@app.get("/api/scheduler/tasks", response_model=List[SchedulerTask])
async def get_scheduler_tasks(request: Request):
    rows = await request.app.state.db.fetch("SELECT id, type, description, status, nextRun, to_email as \"to\", subject, body, date_val as \"date\", interval_seconds as \"interval\", condition, actionDesc, trigger_type, workflow_config, workflow_name FROM scheduler_tasks")
    tasks = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get('workflow_config') is not None:
            try:
                row_dict['workflow_config'] = json.loads(row_dict['workflow_config'])
            except Exception:
                row_dict['workflow_config'] = None
        tasks.append(row_dict)
    return tasks

@app.post("/api/scheduler/task", response_model=SchedulerTask)
async def create_scheduler_task(task_create_data: SchedulerTaskCreate, request: Request):
    import math
    import traceback
    try:
        task_id = str(uuid.uuid4())
        if task_create_data.status is None:
            task_create_data.status = "active"

        # Ensure workflow_config is a JSON-serializable string or None
        workflow_config = task_create_data.workflow_config
        if workflow_config is not None:
            if not isinstance(workflow_config, dict):
                try:
                    workflow_config = json.loads(json.dumps(workflow_config))
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"workflow_config is not serializable: {e}")
            workflow_config = json.dumps(workflow_config)  # Serialize dict to JSON string
        print(f"Creating scheduler task with workflow_config: {workflow_config}")
        await request.app.state.db.execute(
            """
            INSERT INTO scheduler_tasks (id, type, description, status, nextRun, to_email, subject, body, date_val, interval_seconds, condition, actionDesc, trigger_type, workflow_config, workflow_name)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            task_id, task_create_data.type, task_create_data.description, task_create_data.status, None, # nextRun is managed by scheduler
            task_create_data.to, task_create_data.subject, task_create_data.body, task_create_data.date, task_create_data.interval,
            task_create_data.condition, task_create_data.actionDesc, task_create_data.trigger_type, workflow_config, task_create_data.workflow_name
        )

        # Fetch the created task to return the full SchedulerTask model
        created_task_record = await request.app.state.db.fetchrow(
            "SELECT id, type, description, status, nextRun, to_email as \"to\", subject, body, date_val as \"date\", interval_seconds as \"interval\", condition, actionDesc, trigger_type, workflow_config, workflow_name FROM scheduler_tasks WHERE id = $1",
            task_id
        )
        created_task_dict = dict(created_task_record)
        if created_task_dict.get('workflow_config') is not None:
            try:
                created_task_dict['workflow_config'] = json.loads(created_task_dict['workflow_config'])
            except Exception:
                created_task_dict['workflow_config'] = None
        created_task = SchedulerTask(**created_task_dict)

        # Register cron workflow in scheduler if trigger_type is 'cron' and status is 'active'
        if created_task.trigger_type == 'cron' and created_task.status == 'active':
            # Fetch global email grabber frequency settings
            db_pool = request.app.state.db
            freq_type_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_type'")
            freq_value_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_value'")

            freq_type = freq_type_row['value'] if freq_type_row and freq_type_row['value'] else 'days' # Default to 'days'
            freq_value_str = freq_value_row['value'] if freq_value_row and freq_value_row['value'] else '1' # Default to '1'

            interval_seconds = 86400 # Default: 1 Tag
            try:
                freq_value = int(freq_value_str)
                if freq_type == 'days':
                    interval_seconds = freq_value * 86400
                elif freq_type == 'minutes':
                    interval_seconds = freq_value * 60
            except ValueError:
                logging.warning(f"Invalid global frequency_value '{freq_value_str}'. Using default 1 day interval for workflow {created_task.workflow_name} ({created_task.id}).")
                interval_seconds = 86400

            # Definiere die auszuführende Workflow-Funktion
            async def workflow_func():
                print(f"[Scheduler] Triggering workflow {created_task.workflow_name} ({created_task.id}) via cron.")
                # Hier gewünschte Backend-Logik einfügen, z.B. check_new_emails(request.app.state.db)
                pass # TODO: Implementiere die gewünschte Logik
            request.app.state.scheduler.schedule_cron(workflow_func, interval_seconds, created_task.id)
            logging.info(f"Scheduled cron workflow '{created_task.workflow_name}' ({created_task.id}) to run every {interval_seconds} seconds based on global settings.")

        await log_generic_action(
            db_pool=request.app.state.db,
            action_description=f"Workflow '{created_task.workflow_name}' (ID: {created_task.id}) of type '{created_task.trigger_type}' created.",
            username="user_api"
        )
        return created_task
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Error in create_scheduler_task: {e}\n{tb}")
        return JSONResponse(status_code=500, content={"error": str(e), "trace": tb})

@app.post("/api/scheduler/task/{task_id}/pause")
async def pause_scheduler_task(task_id: str, request: Request):
    # First, fetch the current status
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
    # TODO: Update actual scheduler if task was active/paused (AgentScheduler might need methods for this)
    return {"status": new_status}

@app.delete("/api/scheduler/task/{task_id}")
async def delete_scheduler_task(task_id: str, request: Request):
    # First, check if the task exists and get its type for potential unscheduling logic
    task_record = await request.app.state.db.fetchrow("SELECT id, trigger_type FROM scheduler_tasks WHERE id = $1", task_id)
    if not task_record:
        raise HTTPException(status_code=404, detail="Task not found")

    # Delete from database
    result = await request.app.state.db.execute("DELETE FROM scheduler_tasks WHERE id = $1", task_id)
    if result == "DELETE 0": # Should ideally be caught by the check above, but as a safeguard
        raise HTTPException(status_code=404, detail="Task not found after check.")

    # Unscheduling logic from AgentScheduler (veraltet, da nur noch globaler Cronjob)
    # if task_record['trigger_type'] == 'cron':
    #     request.app.state.scheduler.cancel_task(task_id)
    #     logging.info(f"Cancelled cron task {task_id} in scheduler.")

    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Workflow '{task_id}' deleted.",
        username="user_api" # Placeholder
    )
    return {"ok": True}

# Settings Endpoints
@app.get("/api/settings", response_model=SettingsData)
async def get_settings(request: Request):
    db_pool = request.app.state.db

    # Fetch email grabber frequency
    freq_type_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_type'")
    freq_value_row = await db_pool.fetchrow("SELECT value FROM settings WHERE key = 'email_grabber_frequency_value'")

    freq_type = freq_type_row['value'] if freq_type_row and freq_type_row['value'] else 'days' # Default to 'days' if not found or empty
    freq_value = int(freq_value_row['value']) if freq_value_row and freq_value_row['value'] and freq_value_row['value'].isdigit() else 1 # Default to 1 if not found, empty, or not a digit

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

# Individual endpoints for Email Types (if needed for more granular control)
# @app.get("/api/email_types", response_model=List[EmailType])
# async def get_email_types(request: Request):
#     rows = await request.app.state.db.fetch("SELECT id, topic, description FROM email_types ORDER BY topic")
#     return [EmailType(**dict(row)) for row in rows]

# @app.post("/api/email_types", response_model=EmailType)
# async def create_email_type(email_type: EmailType, request: Request):
#     # ... insertion logic ...

# @app.delete("/api/email_types/{email_type_id}")
# async def delete_email_type(email_type_id: int, request: Request):
#     # ... deletion logic ...

# Individual endpoints for Key Features (if needed for more granular control)
# @app.get("/api/key_features", response_model=List[KeyFeature])
# async def get_key_features(request: Request):
#     rows = await request.app.state.db.fetch("SELECT id, name FROM key_features ORDER BY name")
#     return [KeyFeature(**dict(row)) for row in rows]

# @app.post("/api/key_features", response_model=KeyFeature)
# async def create_key_feature(key_feature: KeyFeature, request: Request):
#     # ... insertion logic ...

# @app.delete("/api/key_features/{key_feature_id}")
# async def delete_key_feature(key_feature_id: int, request: Request):
#     # ... deletion logic ...

# User Management Endpoints
@app.post("/api/users/add", response_model=User)
async def addUser(user_create_request: CreateUserRequest):
    hashed_password = pwd_context.hash(user_create_request.password)
    try:
        query = """
            INSERT INTO users (email, password, is_admin, roles, google_id, google_access_token, google_refresh_token)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, email, is_admin, roles, google_id
        """
        row = await app.state.db.fetchrow(
            query,
            user_create_request.email,
            hashed_password,
            user_create_request.is_admin,
            user_create_request.roles,
            user_create_request.google_id,
            '',  # google_access_token leer
            ''   # google_refresh_token leer
        )
        if row:
            created_user = User(**dict(row))
            await log_generic_action(
                db_pool=app.state.db,
                action_description=f"User '{created_user.email}' created. Admin: {created_user.is_admin}, Roles: {created_user.roles}",
                username="admin_api" # Placeholder
            )
            return created_user
        else:
            # This case should ideally not be reached if INSERT RETURNING works as expected
            raise HTTPException(status_code=500, detail="Failed to create user.")
    except UniqueViolationError: # Specific error for duplicate email
        raise HTTPException(status_code=400, detail=f"User with email {user_create_request.email} already exists.")
    except Exception as e:
        # Generic error for other issues
        logging.error(f"Error creating user {user_create_request.email}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while creating the user.")

@app.put("/api/users/{user_identifier}/set", response_model=User)
async def setUser(user_identifier: Union[int, str], user_update_request: UpdateUserRequest):
    # Determine if identifier is email or ID
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format.")
    else:
        raise HTTPException(status_code=400, detail="Invalid user identifier. Must be email or ID.")

    # Fetch existing user
    existing_user_row = await app.state.db.fetchrow(
        f"SELECT id, email, password, is_admin, roles, google_id FROM users WHERE {condition_column} = $1",
        user_identifier
    )
    if not existing_user_row:
        raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found.")

    existing_user = dict(existing_user_row)
    update_fields = {}
    if user_update_request.email is not None and user_update_request.email != existing_user["email"]:
        update_fields["email"] = user_update_request.email
    if user_update_request.password is not None:
        update_fields["password"] = pwd_context.hash(user_update_request.password)
    if user_update_request.is_admin is not None and user_update_request.is_admin != existing_user["is_admin"]:
        update_fields["is_admin"] = user_update_request.is_admin
    if user_update_request.roles is not None and user_update_request.roles != existing_user["roles"]:
        update_fields["roles"] = user_update_request.roles
    if user_update_request.google_id is not None and user_update_request.google_id != existing_user.get("google_id"): # Use .get for safety
        update_fields["google_id"] = user_update_request.google_id
    if user_update_request.google_access_token is not None and user_update_request.google_access_token != existing_user.get("google_access_token"):
        update_fields["google_access_token"] = user_update_request.google_access_token
    if user_update_request.google_refresh_token is not None and user_update_request.google_refresh_token != existing_user.get("google_refresh_token"):
        update_fields["google_refresh_token"] = user_update_request.google_refresh_token

    if not update_fields:
        # Return existing user data if no changes are requested
        return User(**existing_user)

    set_clauses = ", ".join([f"{field} = ${{i+2}}" for i, field in enumerate(update_fields.keys())])
    query = f"UPDATE users SET {set_clauses} WHERE {condition_column} = $1 RETURNING id, email, is_admin, roles, google_id, google_access_token, google_refresh_token"

    try:
        updated_user_row = await app.state.db.fetchrow(query, user_identifier, *update_fields.values())
        if updated_user_row:
            updated_user = User(**dict(updated_user_row))
            await log_generic_action(
                db_pool=app.state.db,
                action_description=f"User '{existing_user['email']}' (ID: {existing_user['id']}) updated. Changes: {json.dumps(update_fields) if update_fields else 'No changes'}",
                username="admin_api" # Placeholder
            )
            return updated_user
        else:
            # Should not happen if user was found initially
            raise HTTPException(status_code=500, detail="Failed to update user.")
    except UniqueViolationError: # Handle email collision if email is being changed
        raise HTTPException(status_code=400, detail=f"Another user with email {user_update_request.email} already exists.")
    except Exception as e:
        logging.error(f"Error updating user {user_identifier}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while updating the user.")

@app.delete("/api/users/{user_identifier}")
async def deleteUser(user_identifier: Union[int, str]):
    # Determine if identifier is email or ID
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format.")
    else:
        raise HTTPException(status_code=400, detail="Invalid user identifier. Must be email or ID.")

    # Fetch user details before attempting deletion for logging
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
        if result == "DELETE 0": # Should ideally be caught by the check above
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

@app.get("/api/users")
async def list_users():
    rows = await app.state.db.fetch("SELECT id, email, is_admin, roles, google_id FROM users")
    return [dict(row) for row in rows]


@app.get("/oauth2callback")
async def oauth2callback(request: Request, code: str = Query(...), state: str = Query(None)): # Corrected signature
    """
    Handles the OAuth2 callback from Google, exchanges the code for tokens,
    and stores the credentials in the database.
    """
    logger.info("-----------------------------------------")
    logger.info(f"Received OAuth2 callback with code: {code}, state: {state}")

    # Extract user ID from state (based on the format used in get_gmail_auth_url)
    user_id = None
    if state and '-' in state:
        try:
            # Assuming state format is "original_state-user_id"
            user_id = int(state.split('-')[-1])
            logger.info(f"Extracted user ID from state: {user_id}")
        except ValueError:
            logger.error(f"Could not parse user ID from state: {state}")
            # Handle invalid state - potentially redirect with an error
            return RedirectResponse(url="http://localhost:5173/settings?auth=failure")
    else:
         logger.error(f"State parameter missing or in unexpected format: {state}")
         # Handle missing or invalid state
         return RedirectResponse(url="http://localhost:5173/settings?auth=failure")


    flow = Flow.from_client_secrets_file(
        './auth/gcp-oauth.keys.json',
        scopes=['https://mail.google.com/'],
        redirect_uri='http://localhost:8001/oauth2callback')

    try:
        # Exchange the authorization code for tokens
        flow.fetch_token(code=code)

        # Get credentials
        credentials = flow.credentials

        # Extract access and refresh tokens
        access_token = credentials.token
        refresh_token = credentials.refresh_token # This might be None if not requested or first time

        logger.info(f"Obtained access token. Refresh token available: {refresh_token is not None}")
        rows = await app.state.db.fetch("SELECT * FROM users")
        logger.info(rows)
        # Save tokens to the database for the user
        db_pool = request.app.state.db
        await db_pool.execute(
            "UPDATE users SET google_access_token = $1, google_refresh_token = $2 WHERE id = $3",
            access_token, refresh_token, user_id
        )

        logger.info(f"Successfully obtained and stored Gmail credentials for user ID: {user_id}")

        # Redirect to a frontend page indicating success
        return RedirectResponse(url="http://localhost:5173/settings?auth=success")

    except Exception as e:
        logger.error(f"Error fetching token or saving credentials: {e}")
        rows = await app.state.db.fetch("SELECT * FROM users")
        logger.error(rows)
        # Redirect to a frontend page indicating failure
        return RedirectResponse(url="http://localhost:5173/settings?auth=failure")

@app.get("/api/oauth-config")
def get_oauth_config():
    path = os.path.join(os.path.dirname(__file__), 'auth/gcp-oauth.keys.json')
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Google OAuth config not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/userinfo")
async def userinfo(request: Request):
    data = await request.json()
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Missing email")
    # Also fetch google_id if it's relevant for userinfo response
    row = await app.state.db.fetchrow("SELECT is_admin, roles, google_id FROM users WHERE email=$1", email)
    logger.info(f"Userinfo query for email: {email} returned row: {row}")
    if not row:
        return {"is_admin": False, "roles": [], "google_id": None} # Ensure consistent response structure
    return {"is_admin": row["is_admin"], "roles": row["roles"], "google_id": row["google_id"]}


@app.get("/api/processing_tasks", response_model=List[ProcessingTask])
async def get_processing_tasks(request: Request):
    query = """
    SELECT
        t.id,
        t.email_id,
        t.status,
        t.created_at,
        t.updated_at,
        e.subject AS email_subject,
        e.sender AS email_sender,
        e.body AS email_body,
        e.received_at AS email_received_at,
        e.label AS email_label,
        e.short_description AS email_short_description,
        t.workflow_type
    FROM tasks t
    LEFT JOIN emails e ON t.email_id = e.id
    ORDER BY t.created_at DESC;
    """
    rows = await request.app.state.db.fetch(query)
    return [dict(row) for row in rows]

# Generic Audit Logging Function
async def log_generic_action(db_pool, action_description: str, username: str = "system_event", email_id: Optional[int] = None):
    """Helper function to log generic actions to audit_trail."""
    try:
        await db_pool.execute(
            "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
            email_id, action_description, username
        )
    except Exception as e:
        logging.error(f"Failed to log generic action '{action_description}' for user '{username}': {e}")


async def log_task_action(db_pool, task_id: int, action: str, user: str = "system_user"):
    """Helper function to log task-specific actions to audit_trail."""
    email_id = None
    task_status = None
    workflow_type = None
    try:
        # Fetch email_id and other details for richer logging
        task_details_record = await db_pool.fetchrow("SELECT email_id, status, workflow_type FROM tasks WHERE id = $1", task_id)
        if task_details_record:
            email_id = task_details_record['email_id']
            task_status = task_details_record['status']
            workflow_type = task_details_record['workflow_type']

        action_details_string = f"{action} (Task ID: {task_id}, Current Status: {task_status}, Workflow: {workflow_type or 'N/A'})"

        await db_pool.execute(
            "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
            email_id, action_details_string, user
        )
    except Exception as e:
        logging.error(f"Failed to log task action '{action}' for task {task_id}, user '{user}': {e}")


@app.post("/api/processing_tasks/{task_id}/validate")
async def validate_task(task_id: int, request: Request):
    # Placeholder logic: Update task status to 'validated'
    # The trigger will automatically update 'updated_at'
    result = await request.app.state.db.execute(
        "UPDATE tasks SET status = 'validated' WHERE id = $1",
        task_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")

    await log_task_action(request.app.state.db, task_id, action="Task validated. Status changed to 'validated'", user="user_api")
    return {"status": "success", "message": f"Task {task_id} marked as validated."}

@app.post("/api/processing_tasks/{task_id}/abort")
async def abort_task(task_id: int, request: Request):
    # Placeholder logic: Update task status to 'aborted'
    # The trigger will automatically update 'updated_at'
    result = await request.app.state.db.execute(
        "UPDATE tasks SET status = 'aborted' WHERE id = $1",
        task_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")

    await log_task_action(request.app.state.db, task_id, action="Task aborted. Status changed to 'aborted'", user="user_api")
    return {"status": "success", "message": f"Task {task_id} marked as aborted."}


@app.post("/api/tasks/{task_id}/status")
async def set_task_status(task_id: int, status_request: SetTaskStatusRequest, request: Request):
    # Update task status
    # The trigger will automatically update 'updated_at'
    result = await request.app.state.db.execute(
        "UPDATE tasks SET status = $1 WHERE id = $2",
        status_request.status, task_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")

    # Log the action
    await log_task_action(request.app.state.db, task_id, action=f"Task status manually set to '{status_request.status}'", user="user_api")

    # Optionally, fetch and return the updated task
    # updated_task = await request.app.state.db.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    # return dict(updated_task)
    return {"status": "success", "message": f"Task {task_id} status updated to {status_request.status}."}

@app.put("/api/scheduler/task/{task_id}", response_model=SchedulerTask)
async def update_scheduler_task(task_id: str, task_update_data: SchedulerTaskCreate, request: Request):
    import traceback
    try:
        # Ensure workflow_config is a JSON-serializable string or None
        workflow_config = task_update_data.workflow_config
        if workflow_config is not None:
            if not isinstance(workflow_config, dict):
                try:
                    workflow_config = json.loads(json.dumps(workflow_config))
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"workflow_config is not serializable: {e}")
            workflow_config = json.dumps(workflow_config)  # Serialize dict to JSON string
        # Update the scheduler task in the DB
        result = await request.app.state.db.execute(
            """
            UPDATE scheduler_tasks SET
                type = $1,
                description = $2,
                status = $3,
                to_email = $4,
                subject = $5,
                body = $6,
                date_val = $7,
                interval_seconds = $8,
                condition = $9,
                actionDesc = $10,
                trigger_type = $11,
                workflow_config = $12,
                workflow_name = $13
            WHERE id = $14
            """,
            task_update_data.type,
            task_update_data.description,
            task_update_data.status,
            task_update_data.to,
            task_update_data.subject,
            task_update_data.body,
            task_update_data.date,
            task_update_data.interval,
            task_update_data.condition,
            task_update_data.actionDesc,
            task_update_data.trigger_type,
            workflow_config,
            task_update_data.workflow_name,
            task_id
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Task not found")
        # Fetch the updated task to return the full SchedulerTask model
        updated_task_record = await request.app.state.db.fetchrow(
            "SELECT id, type, description, status, nextRun, to_email as \"to\", subject, body, date_val as \"date\", interval_seconds as \"interval\", condition, actionDesc, trigger_type, workflow_config, workflow_name FROM scheduler_tasks WHERE id = $1",
            task_id
        )
        updated_task_dict = dict(updated_task_record)
        if updated_task_dict.get('workflow_config') is not None:
            try:
                updated_task_dict['workflow_config'] = json.loads(updated_task_dict['workflow_config'])
            except Exception:
                updated_task_dict['workflow_config'] = None
        # Log the update
        await log_generic_action(
            db_pool=request.app.state.db,
            action_description=f"Workflow '{task_id}' updated.",
            username="user_api" # Placeholder
        )
        return SchedulerTask(**updated_task_dict)
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Error in update_scheduler_task: {e}\n{tb}")
        return JSONResponse(status_code=500, content={"error": str(e), "trace": tb})

@app.post("/api/users/{email}/token")
async def save_user_token(email: str, data: dict, request: Request):
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")
    await request.app.state.db.execute(
        "UPDATE users SET google_access_token=$1 WHERE email=$2", token, email
    )
    return {"status": "ok"}

@app.get("/api/gmail/auth-url")
async def get_gmail_auth_url(request: Request):
    """
    Generates the Gmail OAuth authorization URL and returns it to the frontend.
    Includes user ID in the state parameter.
    """
    logger.info("Generating Gmail OAuth authorization URL...")
    # In a real app, get the user ID from the authenticated request
    # For demonstration, using a placeholder user ID (e.g., 1)
    user_id = 1 # Replace with actual user ID retrieval
    auth_url, state = generate_auth_url() # generate_auth_url already includes a state
    # Append user_id to the state (simple approach, consider signing state in production)
    state_with_user = f"{state}-{user_id}"
    auth_url_with_state = auth_url.replace(f"state={state}", f"state={state_with_user}")

    logger.info(f"Generated auth URL: {auth_url_with_state}")
    return {"auth_url": auth_url_with_state}

# Add endpoint to get MCP auth URL
@app.get("/api/mcp/auth-url")
async def get_mcp_auth_url():
    """
    Provides the frontend with the URL to initiate MCP server login.
    (Placeholder - replace with actual MCP auth URL generation)
    """
    # Replace with the actual URL to initiate MCP server login
    # You might need to pass a redirect_uri parameter to the MCP server
    mcp_login_url = "http://your-mcp-server/auth/login?redirect_uri=http://localhost:8001/mcpcallback"
    return {"auth_url": mcp_login_url}

# Add endpoint to handle MCP callback and save token
@app.get("/mcpcallback")
async def mcp_callback(token: str = Query(...), user_email: str = Query(...)):
    """
    Handles the callback from the MCP server, receives the token,
    and saves it to the database for the specified user.
    (Assumes token and user_email are passed as query parameters)
    """
    logger.info(f"Received MCP callback for user: {user_email}")

    # Find the user by email and save the MCP token
    user_row = await app.state.db.fetchrow("SELECT id FROM users WHERE email = $1", user_email)

    if user_row:
        await app.state.db.execute(
            "UPDATE users SET mcp_token = $1 WHERE id = $2",
            token, user_row['id']
        )
        logger.info(f"MCP token saved for user: {user_email}")
        # Redirect to a frontend page indicating success
        return RedirectResponse(url="http://localhost:5173/settings?mcpauth=success")
    else:
        logger.error(f"User not found for MCP callback: {user_email}")
        # Redirect to a frontend page indicating failure
        return RedirectResponse(url="http://localhost:5173/settings?mcpauth=failure")

# --- AgentScheduler Control Endpoints ---
from fastapi import status as fastapi_status

@app.post("/api/scheduler/start")
async def start_scheduler():
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.start()
        return {"status": "running"}
    return JSONResponse(status_code=500, content={"error": "Scheduler not available"})

@app.post("/api/scheduler/stop")
async def stop_scheduler():
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.cancel_all()
        return {"status": "stopped"}
    return JSONResponse(status_code=500, content={"error": "Scheduler not available"})

@app.get("/api/scheduler/status")
async def scheduler_status():
    if hasattr(app.state, 'scheduler'):
        running = app.state.scheduler.is_running() if hasattr(app.state.scheduler, 'is_running') else None
        if running is True:
            return {"status": "running"}
        elif running is False:
            return {"status": "stopped"}
        else:
            return {"status": "unknown"}
    return JSONResponse(status_code=500, content={"error": "Scheduler not available"})

# --- Endpoint to check if Google refresh token is set for a user ---
@app.get("/api/users/{user_identifier}/has_google_refresh_token")
async def has_google_refresh_token(user_identifier: Union[int, str]):
    # Determine if identifier is email or ID
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format.")
    else:
        raise HTTPException(status_code=400, detail="Invalid user identifier. Must be email or ID.")

    row = await app.state.db.fetchrow(f"SELECT google_refresh_token FROM users WHERE {condition_column} = $1", user_identifier)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    refresh_token = row["google_refresh_token"]
    if not refresh_token or refresh_token in ('', 'none', None):
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Google refresh token not set for this user.")
    return {"has_refresh_token": True}

@app.delete("/api/emails/{email_id}")
async def delete_email(email_id: int, request: Request):
    """Deletes an email by its ID."""
    # Check if email exists before attempting deletion
    existing_email = await request.app.state.db.fetchrow("SELECT id FROM emails WHERE id = $1", email_id)
    if not existing_email:
        raise HTTPException(status_code=404, detail=f"Email with id {email_id} not found")

    result = await request.app.state.db.execute("DELETE FROM emails WHERE id = $1", email_id)

    if result == "DELETE 0":
        # This case should ideally not be reached due to the check above, but as a safeguard
        raise HTTPException(status_code=404, detail=f"Email with id {email_id} not found after check.")

    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Email ID {email_id} deleted.",
        username="user_api", # Placeholder for actual user
        email_id=email_id
    )
    return {"status": "ok", "message": f"Email {email_id} deleted successfully."}

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int, request: Request):
    """Deletes a document by its ID."""
    # Check if document exists before attempting deletion
    existing_document = await request.app.state.db.fetchrow("SELECT id FROM documents WHERE id = $1", document_id)
    if not existing_document:
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found")

    result = await request.app.state.db.execute("DELETE FROM documents WHERE id = $1", document_id)

    if result == "DELETE 0":
        # This case should ideally not be reached due to the check above, but as a safeguard
        raise HTTPException(status_code=404, detail=f"Document with id {document_id} not found after check.")

    await log_generic_action(
        db_pool=request.app.state.db,
        action_description=f"Document ID {document_id} deleted.",
        username="user_api" # Placeholder for actual user
        # No email_id for document deletion directly unless linked
    )
    return {"status": "ok", "message": f"Document {document_id} deleted successfully."}

@app.get("/api/documents", response_model=List[Document])
async def get_documents(request: Request):
    """Lists all documents."""
    rows = await request.app.state.db.fetch("SELECT id, email_id, filename, content_type, data_b64, is_processed, created_at FROM documents ORDER BY created_at DESC")
    return [dict(row) for row in rows]

@app.get("/api/documents/{document_id}/content")
async def get_document_content(document_id: int, request: Request):
    """Fetches the content of a specific document."""
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
