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
from fastapi import FastAPI, WebSocket, Query, Request, Depends, HTTPException, status as fastapi_status
from fastapi.responses import RedirectResponse, JSONResponse, Response
from pydantic import BaseModel
from typing import List, Optional, Union
import json
from passlib.context import CryptContext
try:
    from asyncpg.exceptions import UniqueViolationError
except ImportError:
    UniqueViolationError = None # type: ignore
from dotenv import load_dotenv
import os
import logging
import asyncpg # Keep for app.state.db type hinting if needed elsewhere, but direct calls will be removed
import uuid
import datetime
import base64
from google_auth_oauthlib.flow import Flow # type: ignore
from agent.agent_scheduler import AgentScheduler
from agent.agent_ws import agent_websocket
from agent.email_checker import check_new_emails
from gmail_utils.gmail_auth import generate_auth_url

# Import all necessary functions from db_utils
from .db_utils import (
    get_settings_db, check_if_user_exists_db, create_user_db, get_user_by_email_db, update_user_db,
    get_emails_db, get_email_by_id_db, update_email_label_db, delete_email_from_db,
    get_audit_trail_db, get_scheduler_tasks_db, create_scheduler_task_db, update_scheduler_task_db, delete_scheduler_task_db,
    save_settings_db, list_users_db, update_user_google_tokens_db, get_user_by_id_db, delete_user_db,
    get_processing_tasks_db, update_task_status_db, get_user_access_token_db, check_if_admin_user_exists_db,
    get_document_content_db, get_documents_db, delete_document_from_db,
    log_generic_action_db, log_task_action_db, update_user_mcp_token_db
)
# Remove direct mcp tool imports if they are now fully handled via db_utils or other layers
# from gmail_utils.gmail_mcp_tools_wrapper import (...)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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

# --- Pydantic models ---
# Email/Audit models
class Email(BaseModel):
    """Represents an email message."""
    id: int
    subject: str
    sender: str
    body: str # Consider if this should always be returned, might be large
    label: Optional[str] = None
    type: Optional[str] = None
    short_description: Optional[str] = None
    # document_ids: Optional[List[int]] = None # If you want to include this

class AuditTrail(BaseModel):
    """Represents an audit trail log entry."""
    id: int
    email_id: Optional[int] = None
    task_id: Optional[int] = None # Added task_id
    document_id: Optional[int] = None # Added document_id
    action: str
    username: str
    timestamp: datetime.datetime # Changed to datetime for proper typing

class SchedulerTask(BaseModel):
    """Represents a scheduled task or workflow configuration."""
    id: str # In DB it's int, but example showed str. db_utils returns int.
    type: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    nextRun: Optional[datetime.datetime] = None # Changed to datetime
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None # Consider if this should be datetime
    interval: Optional[int] = None
    condition: Optional[str] = None
    actionDesc: Optional[str] = None
    trigger_type: str
    workflow_config: Optional[dict] = None
    workflow_name: Optional[str] = None
    # Fields from db_utils.get_scheduler_tasks_db that might be missing:
    last_run_at: Optional[datetime.datetime] = None
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None


class SchedulerTaskCreate(BaseModel): # For creating tasks
    type: Optional[str] = None # Maps to 'task_name' in some contexts
    description: Optional[str] = None
    trigger_type: str
    status: str = "active"
    workflow_name: Optional[str] = None # Often used as 'task_name'
    workflow_config: Optional[dict] = None
    # Fields that might go into workflow_config if not direct columns in scheduler_tasks
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None
    interval: Optional[int] = None # Or cron_expression
    condition: Optional[str] = None
    actionDesc: Optional[str] = None
    cron_expression: Optional[str] = None # Explicitly for cron jobs

class CreateUserRequest(BaseModel):
    """Data model for creating a new user."""
    email: str
    password: str
    is_admin: bool = False
    roles: List[str] = []
    google_id: Optional[str] = None # Added for Google OAuth

class UpdateUserRequest(BaseModel):
    """Data model for updating an existing user."""
    email: Optional[str] = None # Allow changing email, though be cautious with this
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    roles: Optional[List[str]] = None
    google_id: Optional[str] = None # Added for Google OAuth
    google_access_token: Optional[str] = None # Field for updating access token
    google_refresh_token: Optional[str] = None # Field for updating refresh token
    mcp_token: Optional[str] = None


class User(BaseModel):
    """Represents a user in the system."""
    id: int
    email: str
    is_admin: bool = False
    roles: List[str] = []
    google_id: Optional[str] = None
    mcp_token: Optional[str] = None # Added for MCP token
    google_access_token: Optional[str] = None # Ensure this is here
    google_refresh_token: Optional[str] = None # Added for Google refresh token
    # created_at: Optional[datetime.datetime] = None # If needed from DB
    # updated_at: Optional[datetime.datetime] = None # If needed from DB


class ProcessingTask(BaseModel):
    """Represents a task for processing an email or document."""
    id: int
    email_id: int
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    email_subject: Optional[str] = None
    email_sender: Optional[str] = None
    # email_body: Optional[str] = None # Usually not listed
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
    content_type: Optional[str] = None # Made optional as DB allows NULL
    # data_b64: str # Not for list views
    is_processed: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None # Added, as it's in DB
    processed_data: Optional[str] = None

# DB pool
@app.on_event("startup")
async def startup():
    """Initializes application state on startup.

    Sets up the database connection pool, initializes the agent scheduler,
    schedules the global email checking cron job based on settings,
    and processes ADMIN_EMAILS environment variable to create initial admin users.
    """
    app.state.db = await asyncpg.create_pool(DATABASE_URL)
    if app.state.db is None:
        logger.error("Database connection pool could not be created.")
        # Potentially raise an exception or exit if DB is critical
        return
    app.state.scheduler = AgentScheduler()

    db_pool = app.state.db
    try:
        settings = await get_settings_db(db_pool)
        freq_type = settings.get('email_grabber_frequency_type', 'days')
        freq_value_str = str(settings.get('email_grabber_frequency_value', '1'))
        
        interval_seconds: int
        if freq_type == 'days':
            interval_seconds = int(freq_value_str) * 86400
        elif freq_type == 'minutes':
            interval_seconds = int(freq_value_str) * 60
        else: # Default or unknown
            interval_seconds = 86400 
        
        app.state.scheduler.schedule_cron(
            'global_email_cron', check_new_emails, interval_seconds, db_pool
        )
        logger.info(f"Scheduled global email checking job to run every {interval_seconds} seconds.")
    except Exception as e:
        logger.error(f"Error scheduling global email checker or fetching settings: {e}")
        # Fallback scheduling if settings fetch failed
        app.state.scheduler.schedule_cron('global_email_cron', check_new_emails, 86400, db_pool)
        logger.info("Scheduled global email checking job with default 24-hour interval due to settings error.")


    admin_emails_str = os.getenv("ADMIN_EMAILS")
    if admin_emails_str:
        admin_emails = [email.strip() for email in admin_emails_str.split(',')]
        default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme_admin")
        hashed_password = pwd_context.hash(default_password)

        for email in admin_emails:
            try:
                user_exists = await check_if_user_exists_db(db_pool, email)
                if not user_exists:
                    await create_user_db(
                        db_pool=db_pool,
                        email=email,
                        hashed_password=hashed_password,
                        is_admin=True,
                        roles=["admin"]
                    )
                    logger.info(f"Admin user {email} created.")
                else:
                    # Ensure existing user is admin
                    user = await get_user_by_email_db(db_pool, email)
                    if user and not user.get('is_admin'):
                        await update_user_db(db_pool, email, {'is_admin': True, 'roles': list(set(user.get('roles', []) + ['admin']))})
                        logger.info(f"Updated existing user {email} to be an admin.")
                    else:
                        logger.info(f"Admin user {email} already exists and is admin.")
            except Exception as e:
                logger.error(f"Error processing admin email {email}: {e}")

@app.on_event("shutdown")
async def shutdown():
    """Cleans up application state on shutdown.

    Cancels all scheduled tasks and closes the database connection pool.
    """
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        app.state.scheduler.cancel_all()
    if hasattr(app.state, 'db') and app.state.db:
        await app.state.db.close()

# Email endpoints
@app.get("/api/emails", response_model=List[Email])
async def get_emails_endpoint(request: Request):
    db_pool = request.app.state.db
    email_rows = await get_emails_db(db_pool)
    return [Email(**email) for email in email_rows]

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_email_endpoint(email_id: int, request: Request):
    db_pool = request.app.state.db
    email_row = await get_email_by_id_db(db_pool, email_id)
    if not email_row:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Email not found")
    return Email(**email_row)

@app.post("/api/emails/{email_id}/label")
async def label_email_endpoint(email_id: int, label: str, request: Request):
    db_pool = request.app.state.db
    success = await update_email_label_db(db_pool, email_id, label)
    if not success:
        # This might happen if the email_id doesn't exist, or update failed for other reasons.
        # get_email_by_id_db could be called first to ensure it exists.
        existing_email = await get_email_by_id_db(db_pool, email_id)
        if not existing_email:
            raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Email with id {email_id} not found.")
        # If it exists but update failed, it's a server error or concurrent modification.
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update email label.")

    await log_generic_action_db(
        db_pool=db_pool,
        action_description=f"Email ID {email_id} labeled as '{label}'",
        username="user_api", # Placeholder for actual user
        email_id=email_id
    )
    return {"status": "ok"}

# Audit Trail endpoints
@app.get("/api/audit", response_model=List[AuditTrail])
async def get_audit_endpoint(request: Request):
    db_pool = request.app.state.db
    audit_rows = await get_audit_trail_db(db_pool, limit=100)
    # Ensure timestamp is correctly formatted if needed by Pydantic model (datetime is fine)
    return [AuditTrail(**row) for row in audit_rows]

# WebSocket for agent chat (MCP integration)
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    """Handles WebSocket connections for agent interactions.

    Args:
        websocket (WebSocket): The WebSocket connection instance.
    """
    await agent_websocket(websocket)

@app.get("/api/scheduler/tasks", response_model=List[SchedulerTask])
async def get_scheduler_tasks_endpoint(request: Request):
    db_pool = request.app.state.db
    tasks_from_db = await get_scheduler_tasks_db(db_pool)
    response_tasks = []
    for task_dict in tasks_from_db:
        # Map db fields to SchedulerTask model fields
        # get_scheduler_tasks_db returns: id, task_name, trigger_type, cron_expression, status, 
        # last_run_at, next_run_at, workflow_config, created_at, updated_at
        mapped_task = {
            "id": str(task_dict.get('id')), # Model expects str ID
            "workflow_name": task_dict.get('task_name'),
            "type": task_dict.get('task_name'), # 'type' in model might map to 'task_name'
            "description": task_dict.get('description', task_dict.get('task_name')), # Fallback for description
            "trigger_type": task_dict.get('trigger_type'),
            "status": task_dict.get('status'),
            "lastRun": task_dict.get('last_run_at'), # Pydantic model uses lastRun, DB has last_run_at
            "nextRun": task_dict.get('next_run_at'), # Pydantic model uses nextRun, DB has next_run_at
            "workflow_config": task_dict.get('workflow_config'), # Already a dict from db_utils
            "created_at": task_dict.get('created_at'),
            "updated_at": task_dict.get('updated_at'),
            # Fields from SchedulerTaskCreate that might be in workflow_config
            "to": task_dict.get('workflow_config', {}).get('to'),
            "subject": task_dict.get('workflow_config', {}).get('subject'),
            "body": task_dict.get('workflow_config', {}).get('body'),
            "date": task_dict.get('workflow_config', {}).get('date'),
            "interval": task_dict.get('workflow_config', {}).get('interval'),
            "condition": task_dict.get('workflow_config', {}).get('condition'),
            "actionDesc": task_dict.get('workflow_config', {}).get('actionDesc')
        }
        response_tasks.append(SchedulerTask(**mapped_task))
    return response_tasks

@app.post("/api/scheduler/task", response_model=SchedulerTask)
async def create_scheduler_task_endpoint(task_create_data: SchedulerTaskCreate, request: Request):
    db_pool = request.app.state.db
    db_task_data = {
        'task_name': task_create_data.workflow_name or task_create_data.description or "Untitled Workflow",
        'trigger_type': task_create_data.trigger_type,
        'cron_expression': task_create_data.cron_expression, # Added cron_expression to Pydantic model
        'status': task_create_data.status,
        'workflow_config': task_create_data.workflow_config or {}
    }
    # Populate workflow_config with other fields from SchedulerTaskCreate
    if task_create_data.to: db_task_data['workflow_config']['to'] = task_create_data.to
    if task_create_data.subject: db_task_data['workflow_config']['subject'] = task_create_data.subject
    if task_create_data.body: db_task_data['workflow_config']['body'] = task_create_data.body
    if task_create_data.date: db_task_data['workflow_config']['date'] = task_create_data.date
    if task_create_data.interval: db_task_data['workflow_config']['interval'] = task_create_data.interval
    if task_create_data.condition: db_task_data['workflow_config']['condition'] = task_create_data.condition
    if task_create_data.actionDesc: db_task_data['workflow_config']['actionDesc'] = task_create_data.actionDesc

    created_task_dict = await create_scheduler_task_db(db_pool, db_task_data)
    if not created_task_dict:
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create scheduler task.")

    # Map db_utils response to SchedulerTask Pydantic model
    response_task = SchedulerTask(
        id=str(created_task_dict.get('id')),
        workflow_name=created_task_dict.get('task_name'),
        type=created_task_dict.get('task_name'),
        description=created_task_dict.get('description', created_task_dict.get('task_name')),
        trigger_type=created_task_dict.get('trigger_type'),
        status=created_task_dict.get('status'),
        lastRun=created_task_dict.get('last_run_at'),
        nextRun=created_task_dict.get('next_run_at'),
        workflow_config=created_task_dict.get('workflow_config'),
        created_at=created_task_dict.get('created_at'),
        updated_at=created_task_dict.get('updated_at'),
        to=created_task_dict.get('workflow_config', {}).get('to'),
        subject=created_task_dict.get('workflow_config', {}).get('subject'),
        body=created_task_dict.get('workflow_config', {}).get('body'),
        date=created_task_dict.get('workflow_config', {}).get('date'),
        interval=created_task_dict.get('workflow_config', {}).get('interval'),
        condition=created_task_dict.get('workflow_config', {}).get('condition'),
        actionDesc=created_task_dict.get('workflow_config', {}).get('actionDesc')
    )
    # log_generic_action_db is called within create_scheduler_task_db
    return response_task

@app.put("/api/scheduler/task/{task_id}", response_model=SchedulerTask)
async def update_scheduler_task_endpoint(task_id: int, task_update_data: SchedulerTaskCreate, request: Request):
    db_pool = request.app.state.db
    # Prepare updates dict for update_scheduler_task_db
    updates_for_db = {
        'task_name': task_update_data.workflow_name or task_update_data.description,
        'trigger_type': task_update_data.trigger_type,
        'cron_expression': task_update_data.cron_expression,
        'status': task_update_data.status,
        'workflow_config': task_update_data.workflow_config or {}
    }
    if task_update_data.to: updates_for_db['workflow_config']['to'] = task_update_data.to
    if task_update_data.subject: updates_for_db['workflow_config']['subject'] = task_update_data.subject
    # ... add other fields to workflow_config as in create endpoint ...

    updated_task_dict = await update_scheduler_task_db(db_pool, task_id, updates_for_db)
    if not updated_task_dict:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Scheduler task not found or not updated.")

    # Map to SchedulerTask Pydantic model (similar to create endpoint)
    response_task = SchedulerTask(
        id=str(updated_task_dict.get('id')),
        workflow_name=updated_task_dict.get('task_name'),
        type=updated_task_dict.get('task_name'),
        description=updated_task_dict.get('description', updated_task_dict.get('task_name')),
        trigger_type=updated_task_dict.get('trigger_type'),
        status=updated_task_dict.get('status'),
        lastRun=updated_task_dict.get('last_run_at'),
        nextRun=updated_task_dict.get('next_run_at'),
        workflow_config=updated_task_dict.get('workflow_config'),
        created_at=updated_task_dict.get('created_at'),
        updated_at=updated_task_dict.get('updated_at'),
        to=updated_task_dict.get('workflow_config', {}).get('to'),
        subject=updated_task_dict.get('workflow_config', {}).get('subject'),
        body=updated_task_dict.get('workflow_config', {}).get('body')
        # ... etc.
    )
    # log_generic_action_db is called within update_scheduler_task_db
    return response_task

@app.post("/api/scheduler/task/{task_id}/pause")
async def pause_scheduler_task_endpoint(task_id: int, request: Request):
    db_pool = request.app.state.db
    # Fetch current task to determine new status
    tasks_from_db = await get_scheduler_tasks_db(db_pool)
    current_task_dict = next((task for task in tasks_from_db if task.get('id') == task_id), None)

    if not current_task_dict:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    current_status = current_task_dict.get('status')
    new_status = "paused" if current_status == "active" else "active"
    
    updated_task = await update_scheduler_task_db(db_pool, task_id, {"status": new_status})
    if not updated_task:
        # This might indicate a concurrent modification or other issue
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update task status.")

    # log_generic_action_db is called within update_scheduler_task_db
    return {"status": new_status, "id": task_id}

@app.delete("/api/scheduler/task/{task_id}")
async def delete_scheduler_task_endpoint(task_id: int, request: Request):
    db_pool = request.app.state.db
    deleted = await delete_scheduler_task_db(db_pool, task_id)
    if not deleted:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Task not found or could not be deleted.")
    
    # Consider if delete_scheduler_task_db should also log, or if it's done here.
    # For consistency, if create/update log in db_utils, delete could too.
    # If not, log here:
    await log_generic_action_db(
        db_pool=db_pool,
        action_description=f"Workflow ID '{task_id}' deleted.",
        username="user_api" # Placeholder
    )
    return {"ok": True, "message": f"Task {task_id} deleted successfully."}

# Settings Endpoints
@app.get("/api/settings", response_model=SettingsData)
async def get_settings_endpoint(request: Request):
    db_pool = request.app.state.db
    settings_dict = await get_settings_db(db_pool)
    # Ensure the structure matches SettingsData model, converting if necessary
    return SettingsData(
        email_grabber_frequency_type=settings_dict.get('email_grabber_frequency_type', 'days'),
        email_grabber_frequency_value=int(settings_dict.get('email_grabber_frequency_value', 1)), # Ensure int
        email_types=[EmailType(**et) for et in settings_dict.get('email_types', [])],
        key_features=[KeyFeature(**kf) for kf in settings_dict.get('key_features', [])]
    )

@app.post("/api/settings")
async def save_settings_endpoint(settings_data: SettingsData, request: Request):
    db_pool = request.app.state.db
    # save_settings_db expects a dictionary
    await save_settings_db(db_pool, settings_data.model_dump())
    await log_generic_action_db(
        db_pool=db_pool,
        action_description="Settings updated (Email Grabber Frequency, Email Types, Key Features)",
        username="user_api" # Placeholder
    )
    return {"status": "success", "message": "Settings saved successfully"}

# User Management Endpoints
@app.post("/api/users/add", response_model=User)
async def addUser_endpoint(user_create_request: CreateUserRequest, request: Request):
    db_pool = request.app.state.db
    hashed_password = pwd_context.hash(user_create_request.password)
    try:
        created_user_dict = await create_user_db(
            db_pool=db_pool,
            email=user_create_request.email,
            hashed_password=hashed_password,
            is_admin=user_create_request.is_admin,
            roles=user_create_request.roles,
            google_id=user_create_request.google_id
        )
        # create_user_db returns a dict that should align with User model (excluding password)
        # Ensure User model does not expect password_hash directly
        response_user_data = {k: v for k, v in created_user_dict.items() if k != 'password'}
        created_user = User(**response_user_data)

        await log_generic_action_db(
            db_pool=db_pool,
            action_description=f"User '{created_user.email}' created. Admin: {created_user.is_admin}, Roles: {created_user.roles}",
            username="admin_api" # Placeholder
        )
        return created_user
    except UniqueViolationError:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=f"User with email {user_create_request.email} already exists.")
    except Exception as e:
        logger.error(f"Error creating user {user_create_request.email}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while creating the user.")

@app.put("/api/users/{user_identifier}/set", response_model=User)
async def setUser_endpoint(user_identifier: Union[int, str], user_update_request: UpdateUserRequest, request: Request):
    db_pool = request.app.state.db
    updates = user_update_request.model_dump(exclude_unset=True)
    
    if "password" in updates and updates["password"] is not None:
        updates["password"] = pwd_context.hash(updates["password"])
    elif "password" in updates and updates["password"] is None:
        del updates["password"] # Don't update password if explicitly None

    if not updates:
        # If no updates, fetch and return current user data
        current_user_data = None
        if isinstance(user_identifier, str) and "@" in user_identifier:
            current_user_data = await get_user_by_email_db(db_pool, user_identifier)
        else:
            try:
                user_id = int(user_identifier)
                current_user_data = await get_user_by_id_db(db_pool, user_id)
            except ValueError:
                raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format.")
        if not current_user_data:
            raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="User not found.")
        return User(**{k: v for k,v in current_user_data.items() if k != 'password'})

    try:
        updated_user_dict = await update_user_db(db_pool, user_identifier, updates)
        if not updated_user_dict:
            raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"User with identifier '{user_identifier}' not found or update failed.")
        
        response_user_data = {k: v for k, v in updated_user_dict.items() if k != 'password'}
        updated_user = User(**response_user_data)

        changes_logged = {k: v for k, v in updates.items() if k != "password"}
        if "password" in updates: changes_logged["password"] = "updated"
        
        await log_generic_action_db(
            db_pool=db_pool,
            action_description=f"User '{updated_user.email}' (ID: {updated_user.id}) updated. Changes: {json.dumps(changes_logged)}",
            username="admin_api" # Placeholder
        )
        return updated_user
    except UniqueViolationError: # If email is being changed and it collides
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=f"Another user with the new email already exists.")
    except Exception as e:
        logger.error(f"Error updating user {user_identifier}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred while updating the user: {str(e)}")

@app.delete("/api/users/{user_identifier}")
async def deleteUser_endpoint(user_identifier: Union[int, str], request: Request):
    db_pool = request.app.state.db
    user_to_delete = None
    if isinstance(user_identifier, str) and "@" in user_identifier:
        user_to_delete = await get_user_by_email_db(db_pool, user_identifier)
    else:
        try:
            user_id = int(user_identifier)
            user_to_delete = await get_user_by_id_db(db_pool, user_id)
        except ValueError:
            raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format.")

    if not user_to_delete:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"User with identifier '{user_identifier}' not found.")

    deleted = await delete_user_db(db_pool, user_identifier)
    if not deleted:
        # This might happen if the user was deleted between the fetch and the delete call
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"User with identifier '{user_identifier}' not found during delete operation or delete failed.")

    await log_generic_action_db(
        db_pool=db_pool,
        action_description=f"User '{user_to_delete['email']}' (ID: {user_to_delete['id']}) deleted.",
        username="admin_api" # Placeholder
    )
    return {"status": "success", "message": f"User with identifier '{user_identifier}' deleted successfully."}

@app.get("/api/users", response_model=List[User])
async def list_users_endpoint(request: Request):
    db_pool = request.app.state.db
    users_list_from_db = await list_users_db(db_pool)
    # Ensure password hash is not included in the response
    response_users = []
    for user_data in users_list_from_db:
        user_data_no_pwd = {k:v for k,v in user_data.items() if k != 'password'}
        response_users.append(User(**user_data_no_pwd))
    return response_users

@app.post("/api/users/{email}/token")
async def save_user_token_endpoint(email: str, data: dict, request: Request):
    db_pool = request.app.state.db
    token = data.get("token") # Assuming this is for google_access_token
    if not token:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Token is required in the request data.")
    
    user_exists = await check_if_user_exists_db(db_pool, email)
    if not user_exists:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"User with email {email} not found.")

    # Using update_user_db to set the google_access_token
    updated_user = await update_user_db(db_pool, email, {'google_access_token': token})
    if not updated_user:
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update user token.")

    await log_generic_action_db(
        db_pool=db_pool, 
        action_description=f"Google access token updated for user {email}.", 
        username="user_api_token_update"
    )
    return {"status": "ok"}

@app.get("/oauth2callback")
async def oauth2callback_endpoint(request: Request, code: str = Query(...), state: str = Query(None)):
    db_pool = request.app.state.db
    logger.info("-----------------------------------------")
    logger.info(f"Received OAuth2 callback with code: {code}, state: {state}")
    user_id = None
    if state and '-' in state:
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

    client_secrets_path = os.path.join(os.path.dirname(__file__), 'auth/gcp-oauth.keys.json')
    if not os.path.exists(client_secrets_path):
        logger.error(f"OAuth client secrets file not found at: {client_secrets_path}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OAuth client configuration error.")

    flow = Flow.from_client_secrets_file(
        client_secrets_path,
        scopes=['https://mail.google.com/'],
        redirect_uri='http://localhost:8001/oauth2callback')

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        access_token = credentials.token
        refresh_token = credentials.refresh_token
        logger.info(f"Obtained access token for user ID {user_id}. Refresh token available: {refresh_token is not None}")
        
        await update_user_google_tokens_db(db_pool, user_id, access_token, refresh_token)
        
        logger.info(f"Successfully stored Gmail credentials for user ID: {user_id}")
        await log_generic_action_db(db_pool, f"Gmail OAuth tokens updated for user ID {user_id}.", username=f"user_id_{user_id}")
        return RedirectResponse(url="http://localhost:5173/settings?auth=success")
    except Exception as e:
        logger.error(f"Error during OAuth token exchange or DB update for user ID {user_id}: {e}")
        await log_generic_action_db(db_pool, f"Gmail OAuth token exchange/update failed for user ID {user_id}. Error: {e}", username=f"user_id_{user_id}")
        return RedirectResponse(url="http://localhost:5173/settings?auth=failure_token_exchange")

@app.get("/mcpcallback")
async def mcp_callback_endpoint(request: Request, token: str = Query(...), user_email: str = Query(...)):
    db_pool = request.app.state.db
    user = await get_user_by_email_db(db_pool, user_email)
    if user:
        success = await update_user_mcp_token_db(db_pool, user_email, token)
        if success:
            logger.info(f"MCP token saved successfully for user: {user_email}")
            await log_generic_action_db(db_pool=db_pool, action_description=f"MCP token associated for user {user_email}.", username=user_email)
            return RedirectResponse(url="http://localhost:5173/settings?mcpauth=success")
        else:
            logger.error(f"Failed to update MCP token for user: {user_email}")
            await log_generic_action_db(db_pool=db_pool, action_description=f"MCP token update failed for user {user_email}.", username=user_email)
            return RedirectResponse(url="http://localhost:5173/settings?mcpauth=failure_db_update")
    else:
        logger.error(f"User not found for MCP callback: {user_email}")
        return RedirectResponse(url="http://localhost:5173/settings?mcpauth=failure_user_not_found")

# Processing Task Endpoints
@app.get("/api/processing_tasks", response_model=List[ProcessingTask])
async def get_processing_tasks_endpoint(request: Request):
    db_pool = request.app.state.db
    tasks_data = await get_processing_tasks_db(db_pool)
    return [ProcessingTask(**task) for task in tasks_data]

@app.post("/api/processing_tasks/{task_id}/validate")
async def validate_task_endpoint(task_id: int, request: Request):
    db_pool = request.app.state.db
    # update_task_status_db calls log_task_action_db internally
    updated = await update_task_status_db(db_pool, task_id, 'validated', user="user_api")
    if not updated:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Task with id {task_id} not found or not updated.")
    return {"status": "success", "message": f"Task {task_id} marked as validated."}

@app.post("/api/processing_tasks/{task_id}/abort")
async def abort_task_endpoint(task_id: int, request: Request):
    db_pool = request.app.state.db
    updated = await update_task_status_db(db_pool, task_id, 'aborted', user="user_api")
    if not updated:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Task with id {task_id} not found or not updated.")
    return {"status": "success", "message": f"Task {task_id} marked as aborted."}

@app.post("/api/tasks/{task_id}/status") # Note: path uses /api/tasks/ not /api/processing_tasks/
async def set_task_status_endpoint(task_id: int, status_request: SetTaskStatusRequest, request: Request):
    db_pool = request.app.state.db
    updated = await update_task_status_db(db_pool, task_id, status_request.status, user="user_api")
    if not updated:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Task with id {task_id} not found or not updated.")
    return {"status": "success", "message": f"Task {task_id} status updated to {status_request.status}."}

# Document Endpoints
@app.delete("/api/documents/{document_id}")
async def delete_document_endpoint(document_id: int, request: Request):
    db_pool = request.app.state.db
    # Check if document exists before attempting to delete
    doc_exists = await get_document_content_db(db_pool, document_id) 
    if not doc_exists:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Document with id {document_id} not found.")

    deleted = await delete_document_from_db(db_pool, document_id)
    if not deleted:
        # This might occur if the document was deleted between the check and this call, though unlikely with await.
        # Or if delete_document_from_db had an internal issue not raising an exception but returning False.
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete document {document_id}.")

    await log_generic_action_db(
        db_pool=db_pool,
        action_description=f"Document ID {document_id} deleted from database.",
        username="user_api", # Placeholder
        document_id=document_id
    )
    return {"status": "ok", "message": f"Document {document_id} deleted successfully from database."}

@app.get("/api/documents", response_model=List[Document])
async def get_documents_endpoint(request: Request):
    db_pool = request.app.state.db
    documents_list = await get_documents_db(db_pool)
    # Ensure the Document model is correctly mapping fields from get_documents_db
    return [Document(**doc) for doc in documents_list]

@app.get("/api/documents/{document_id}/content")
async def get_document_content_endpoint(document_id: int, request: Request):
    db_pool = request.app.state.db
    doc_data = await get_document_content_db(db_pool, document_id)
    if not doc_data:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Document with id {document_id} not found")
    
    data_b64 = doc_data.get('data_b64')
    if not data_b64:
        # This case should ideally be handled if a document can exist without data_b64
        logger.error(f"Document {document_id} found but has no data_b64 content.")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Document with id {document_id} has no content.")

    try:
        content_bytes = base64.b64decode(data_b64)
    except Exception as e:
        logger.error(f"Error decoding base64 for document {document_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error decoding document content")
    
    filename = doc_data.get('filename', f'document_{document_id}') # Fallback filename
    media_type = doc_data.get('content_type', 'application/octet-stream')
    return Response(content=content_bytes, media_type=media_type, headers={'Content-Disposition': f'inline; filename="{filename}"'})

# Scheduler Control Endpoints
@app.post("/api/scheduler/start")
async def start_scheduler_endpoint(request: Request):
    db_pool = request.app.state.db
    if hasattr(request.app.state, 'scheduler') and request.app.state.scheduler:
        request.app.state.scheduler.start()
        logger.info("Agent scheduler started via API request.")
        await log_generic_action_db(db_pool=db_pool, action_description="Agent scheduler started.", username="system_api")
        return {"status": "running"}
    logger.error("Attempted to start scheduler, but scheduler not found in app.state.")
    raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler not available or not initialized.")

@app.post("/api/scheduler/stop")
async def stop_scheduler_endpoint(request: Request):
    db_pool = request.app.state.db
    if hasattr(request.app.state, 'scheduler') and request.app.state.scheduler:
        request.app.state.scheduler.cancel_all()
        logger.info("Agent scheduler stopped and tasks cancelled via API request.")
        await log_generic_action_db(db_pool=db_pool, action_description="Agent scheduler stopped and tasks cancelled.", username="system_api")
        return {"status": "stopped"}
    logger.error("Attempted to stop scheduler, but scheduler not found in app.state.")
    raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler not available or not initialized.")

@app.get("/api/scheduler/status")
async def scheduler_status_endpoint(request: Request): # Added request to align with others, though db_pool not directly used here
    if hasattr(request.app.state, 'scheduler') and request.app.state.scheduler:
        is_running = hasattr(request.app.state.scheduler, 'is_running') and request.app.state.scheduler.is_running()
        status_str = "running" if is_running else "stopped"
        # If is_running() can return None or other states, adjust logic:
        # actual_status = request.app.state.scheduler.is_running() if hasattr(request.app.state.scheduler, 'is_running') else None
        # if actual_status is True: status_str = "running"
        # elif actual_status is False: status_str = "stopped"
        # else: status_str = "unknown"
        logger.debug(f"Scheduler status requested: {status_str}")
        return {"status": status_str}
    logger.error("Attempted to get scheduler status, but scheduler not found in app.state.")
    raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler not available or not initialized.")

# Ensure all other endpoints like /api/gmail/auth-url are also checked for direct DB calls if any were missed.
# The /api/users/{user_identifier}/has_google_refresh_token endpoint was previously refactored.
