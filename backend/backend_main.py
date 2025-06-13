'''Main FastAPI application for the ad1 platform.

This module defines the FastAPI application, including CORS middleware,
database connection setup (PostgreSQL with asyncpg), background task scheduling,
API endpoints for managing emails, documents, users, audit trails,
scheduler tasks, application settings, and handles OAuth2 authentication flows.
It also integrates with Gmail API for email operations and provides
WebSocket support for real-time agent interactions.
'''
# FastAPI backend for Ornex Mail
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, Query, Request, Depends, HTTPException, status as fastapi_status
from fastapi.responses import RedirectResponse, JSONResponse, Response

from pydantic import BaseModel
from typing import List, Optional, Union, Dict, Any
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
import debugpy


# Import all necessary functions from db_utils
from db_utils import (
    get_settings_db, check_if_user_exists_db, create_user_db, get_user_by_email_db, update_user_db,
    get_emails_db, get_email_by_id_db, update_email_label_db, delete_email_from_db,
    get_audit_trail_db, get_scheduler_tasks_db, create_scheduler_task_db, update_scheduler_task_db, delete_scheduler_task_db,
    save_settings_db, list_users_db, update_user_google_tokens_db, get_user_by_id_db, delete_user_db,
    get_processing_tasks_db, update_task_status_db, get_user_access_token_db, check_if_admin_user_exists_db,
    get_document_content_db, get_documents_db, delete_document_from_db, get_documents_by_email_id_db,
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

# New Attachment model
class Attachment(BaseModel):
    '''Represents an email attachment.'''
    id: int
    filename: str
    content_type: Optional[str] = None
    thumbnail_base64: Optional[str] = None # For image hover previews

# Email/Audit models
class Email(BaseModel):
    '''Represents an email message.'''
    id: int
    subject: str
    sender: str
    body: str # Consider if this should always be returned, might be large
    received_at: datetime.datetime # Added received_at to the model
    label: Optional[str] = None
    type: Optional[str] = None
    short_description: Optional[str] = None
    document_ids: Optional[List[int]] = None # Keep document_ids for internal use if needed
    attachments: List[Attachment] = [] # Add attachments list

class AuditTrail(BaseModel):
    '''Represents an audit trail log entry.'''
    id: int
    event_type: str # Changed from action to event_type to match DB
    username: str
    timestamp: datetime.datetime # Changed to datetime for proper typing
    data: Optional[Dict[str, Any]] = None # Ensure data is expected as dict

class SchedulerTask(BaseModel):
    '''Represents a scheduled task or workflow configuration.'''
    id: str # In DB it's int, but example showed str. db_utils returns int.
    type: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None # Consider if this should be datetime
    condition: Optional[str] = None
    actionDesc: Optional[str] = None
    workflow_config: Optional[dict] = None
    task_name: Optional[str] = None
    # Fields from db_utils.get_scheduler_tasks_db that might be missing:
    last_run_at: Optional[datetime.datetime] = None
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None


class SchedulerTaskCreate(BaseModel):
    '''Data model for creating a new scheduler task.'''
    type: Optional[str] = None # Maps to 'task_name' in some contexts
    description: Optional[str] = None
    status: str = "active"
    task_name: Optional[str] = None # Often used as 'task_name'
    workflow_config: Optional[dict] = None
    # Fields that might go into workflow_config if not direct columns in scheduler_tasks
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None
    condition: Optional[str] = None
    actionDesc: Optional[str] = None

class CreateUserRequest(BaseModel):
    '''Data model for creating a new user.'''
    email: str
    password: str
    is_admin: bool = False
    roles: List[str] = []
    google_id: Optional[str] = None # Added for Google OAuth

class UpdateUserRequest(BaseModel):
    '''Data model for updating an existing user.'''
    email: Optional[str] = None # Allow changing email, though be cautious with this
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    roles: Optional[List[str]] = None
    google_id: Optional[str] = None # Added for Google OAuth
    google_access_token: Optional[str] = None # Field for updating access token
    google_refresh_token: Optional[str] = None # Field for updating refresh token
    mcp_token: Optional[str] = None


class User(BaseModel):
    '''Represents a user in the system.'''
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
    '''Represents a task for processing an email or document.'''
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
    '''Represents a configurable email type/topic for classification.'''
    id: Optional[int] = None # ID is optional for creation
    topic: str
    description: Optional[str] = None

class KeyFeature(BaseModel):
    '''Represents a configurable key feature for workflow association.'''
    id: Optional[int] = None # ID is optional for creation
    name: str

class SettingsData(BaseModel):
    '''Data model for application settings.'''
    email_grabber_frequency_type: str
    email_grabber_frequency_value: int
    email_types: List[EmailType]
    key_features: List[KeyFeature]

class SetTaskStatusRequest(BaseModel):
    '''Data model for setting the status of a task.'''
    status: str

# Document model
class Document(BaseModel):
    '''Represents a document, typically an email attachment.'''
    id: int
    email_id: int
    filename: str
    content_type: Optional[str] = None # Made optional as DB allows NULL
    data_b64: Optional[str] = None # Re-enabled for frontend preview
    is_processed: bool
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None # Added, as it's in DB
    processed_data: Optional[str] = None

# DB pool
@app.on_event("startup")
async def startup():
    '''Initializes application state on startup.

    Sets up the database connection pool, initializes the agent scheduler,
    schedules the global email checking cron job based on settings,
    and processes ADMIN_EMAILS environment variable to create initial admin users.
    '''
    debugpy.listen(("0.0.0.0", 5678))
    logger.info("Debugger is listening on port 5678. Waiting for attach...")
    # debugpy.wait_for_client() # Optional: uncomment if you want to pause until debugger attaches

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
    '''Cleans up application state on shutdown.

    Cancels all scheduled tasks and closes the database connection pool.
    '''
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        app.state.scheduler.cancel_all()
    if hasattr(app.state, 'db') and app.state.db:
        await app.state.db.close()

# Email endpoints
@app.get("/api/emails", response_model=List[Email])
async def get_emails(request: Request):
    '''
    Retrieves a list of all emails with their attachments.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of email objects including attachment details.
    :rtype: List[Email]
    '''
    db_pool = request.app.state.db
    email_rows = await get_emails_db(db_pool)
    emails_with_attachments = []

    for email_row in email_rows:
        email_dict = dict(email_row)
        attachments_list = []
        document_ids = email_dict.get('document_ids')

        if document_ids:
            for doc_id in document_ids:
                # Fetch minimal document details for the attachment list
                # get_document_content_db fetches data_b64, which might be too much for a list view.
                # A new DB function might be better, but for now, let's use get_document_content_db
                # and only include necessary fields in the Attachment model.
                doc_data = await get_document_content_db(db_pool, doc_id)
                if doc_data:
                    attachments_list.append(Attachment(
                        id=doc_data.get('id'),
                        filename=doc_data.get('filename'),
                        content_type=doc_data.get('content_type'),
                        # thumbnail_base64 is not stored in DB currently, so it will be None
                        thumbnail_base64=None 
                    ))
        
        # Ensure received_at is a datetime object
        if isinstance(email_dict.get('received_at'), datetime.datetime):
             email_dict['received_at'] = email_dict['received_at']
        else:
             # Attempt to parse if it's a string, or set to now/None if parsing fails
             try:
                 email_dict['received_at'] = datetime.datetime.fromisoformat(str(email_dict.get('received_at')))
             except (ValueError, TypeError):
                 email_dict['received_at'] = datetime.datetime.now() # Fallback

        emails_with_attachments.append(Email(
            **email_dict,
            attachments=attachments_list
        ))

    return emails_with_attachments

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_email(email_id: int, request: Request):
    '''
    Retrieves a specific email by its ID, including attachment details.

    :param email_id: The ID of the email to retrieve.
    :type email_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the email with the given ID is not found (status code 404).
    :returns: The email details including attachment details.
    :rtype: Email
    '''
    db_pool = request.app.state.db
    email_row = await get_email_by_id_db(db_pool, email_id)
    if not email_row:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Email not found")

    email_dict = dict(email_row)
    attachments_list = []
    document_ids = email_dict.get('document_ids')

    if document_ids:
        for doc_id in document_ids:
            # Fetch minimal document details for the attachment list
            doc_data = await get_document_content_db(db_pool, doc_id)
            if doc_data:
                attachments_list.append(Attachment(
                    id=doc_data.get('id'),
                    filename=doc_data.get('filename'),
                    content_type=doc_data.get('content_type'),
                    thumbnail_base64=None # thumbnail_base64 is not stored in DB currently
                ))

    # Ensure received_at is a datetime object
    if isinstance(email_dict.get('received_at'), datetime.datetime):
         email_dict['received_at'] = email_dict['received_at']
    else:
         try:
             email_dict['received_at'] = datetime.datetime.fromisoformat(str(email_dict.get('received_at')))
         except (ValueError, TypeError):
             email_dict['received_at'] = datetime.datetime.now() # Fallback

    return Email(
        **email_dict,
        attachments=attachments_list
    )


@app.post("/api/emails/{email_id}/label")
async def label_email_endpoint(email_id: int, label: str, request: Request):
    '''
    Updates the label of a specific email.

    :param email_id: The ID of the email to label.
    :type email_id: int
    :param label: The new label to apply to the email.
    :type label: str
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the email is not found (404) or if the update fails (500).
    :returns: A status confirmation.
    :rtype: Dict[str, str]
    '''
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
    return {"status": "ok"}

# Audit Trail endpoints
@app.get("/api/audit", response_model=List[AuditTrail])
async def get_audit(request: Request):
    '''
    Retrieves the latest audit trail entries.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of audit trail entries.
    :rtype: List[AuditTrail]
    '''
    db_pool = request.app.state.db
    audit_rows = await get_audit_trail_db(db_pool, limit=100)
    # Ensure timestamp is correctly formatted if needed by Pydantic model (datetime is fine)
    return [AuditTrail(**row) for row in audit_rows]

# WebSocket for agent chat (MCP integration)
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    '''Handles WebSocket connections for agent interactions.

    :param websocket: The WebSocket connection instance.
    :type websocket: WebSocket
    '''
    await agent_websocket(websocket)

@app.get("/api/scheduler/tasks", response_model=List[SchedulerTask])
async def get_scheduler_tasks(request: Request):
    '''
    Retrieves a list of all scheduler tasks (workflows).

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of scheduler task objects.
    :rtype: List[SchedulerTask]
    '''
    db_pool = request.app.state.db
    tasks_from_db = await get_scheduler_tasks_db(db_pool)
    response_tasks = []
    logger.info(f"Retrieved {len(tasks_from_db)} tasks from the database.") 
    for task_dict in tasks_from_db:
        # Map db fields to SchedulerTask model fields
        # get_scheduler_tasks_db returns: id, task_name, type, description, status, 
        # last_run_at, workflow_config, created_at, updated_at
        mapped_task = {
            "id": str(task_dict.get('id')), # Model expects str ID
            "task_name": task_dict.get('task_name'),
            "type": task_dict.get('type'), 
            "description": task_dict.get('description', task_dict.get('task_name')), # Fallback for description
            "status": task_dict.get('status'),
            "last_run_at": task_dict.get('last_run_at'), # Corrected from lastRun
            # "next_run_at": task_dict.get('next_run_at'), # REMOVED
            "workflow_config": task_dict.get('workflow_config'), # Already a dict from db_utils
            "created_at": task_dict.get('created_at'),
            "updated_at": task_dict.get('updated_at'),
            # Fields from SchedulerTaskCreate that might be in workflow_config
            "to": task_dict.get('workflow_config', {}).get('to'),
            "subject": task_dict.get('workflow_config', {}).get('subject'),
            "body": task_dict.get('workflow_config', {}).get('body'),
            "date": task_dict.get('workflow_config', {}).get('date'),
            # "interval": task_dict.get('workflow_config', {}).get('interval'), # REMOVED
            "condition": task_dict.get('workflow_config', {}).get('condition'),
            "actionDesc": task_dict.get('workflow_config', {}).get('actionDesc')
        }
        response_tasks.append(SchedulerTask(**mapped_task))
    return response_tasks

@app.post("/api/scheduler/task", response_model=SchedulerTask)
async def create_scheduler_task(task_create_data: SchedulerTaskCreate, request: Request):
    '''
    Creates a new scheduler task (workflow).

    :param task_create_data: The data for creating the new scheduler task.
    :type task_create_data: SchedulerTaskCreate
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task creation fails in the database (500).
    :returns: The created scheduler task object.
    :rtype: SchedulerTask
    '''
    db_pool = request.app.state.db
    db_task_data = {
        'task_name': task_create_data.task_name or task_create_data.description or "Untitled Workflow",
        'type': task_create_data.type,
        'description': task_create_data.description,
        'status': task_create_data.status,
        'workflow_config': task_create_data.workflow_config or {},
        # 'trigger_type' is no longer part of SchedulerTaskCreate or db_task_data
    }
    logger.info(f"Creating scheduler task with data: {db_task_data}")
    # ID is generated within create_scheduler_task_db now
    # task_id= str(uuid.uuid4()) 
    # db_task_data['id'] = task_id 
    
    created_task_dict = await create_scheduler_task_db(db_pool, db_task_data)
    if not created_task_dict:
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create scheduler task.")

    # Map db_utils response to SchedulerTask Pydantic model
    response_task = SchedulerTask(
        id=str(created_task_dict.get('id')),
        task_name=created_task_dict.get('task_name'),
        type=created_task_dict.get('type'),
        description=created_task_dict.get('description', created_task_dict.get('task_name')),
        # trigger_type=created_task_dict.get('trigger_type'), # REMOVED
        status=created_task_dict.get('status'),
        last_run_at=created_task_dict.get('last_run_at'),
        # next_run_at=created_task_dict.get('next_run_at'), # REMOVED
        workflow_config=created_task_dict.get('workflow_config'),
        created_at=created_task_dict.get('created_at'),
        updated_at=created_task_dict.get('updated_at'),
        to=created_task_dict.get('workflow_config', {}).get('to'),
        subject=created_task_dict.get('workflow_config', {}).get('subject'),
        body=created_task_dict.get('workflow_config', {}).get('body'),
        date=created_task_dict.get('workflow_config', {}).get('date'),
        # interval=created_task_dict.get('workflow_config', {}).get('interval'), # REMOVED
        condition=created_task_dict.get('workflow_config', {}).get('condition'),
        actionDesc=created_task_dict.get('workflow_config', {}).get('actionDesc')
    )
    return response_task

@app.put("/api/scheduler/task/{task_id}", response_model=SchedulerTask)
async def update_scheduler_task(task_id: str, task_update_data: SchedulerTaskCreate, request: Request): # Changed task_id to str
    '''
    Updates an existing scheduler task (workflow).

    :param task_id: The ID of the scheduler task to update.
    :type task_id: str
    :param task_update_data: The data to update the scheduler task with.
    :type task_update_data: SchedulerTaskCreate
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task is not found or update fails (404).
    :returns: The updated scheduler task object.
    :rtype: SchedulerTask
    '''
    db_pool = request.app.state.db
    # Prepare updates dict for update_scheduler_task_db
    updates_for_db = {
        'task_name': task_update_data.task_name or task_update_data.description,
        'type': task_update_data.type,
        'description': task_update_data.description,
        # 'trigger_type': task_update_data.trigger_type, # REMOVED
        'status': task_update_data.status,
        'workflow_config': task_update_data.workflow_config or {}
    }
    # Remove None values to avoid overwriting existing fields with None if not provided
    updates_for_db = {k: v for k, v in updates_for_db.items() if v is not None}

    if task_update_data.to: updates_for_db.setdefault('workflow_config', {})['to'] = task_update_data.to
    if task_update_data.subject: updates_for_db.setdefault('workflow_config', {})['subject'] = task_update_data.subject
    if task_update_data.body: updates_for_db.setdefault('workflow_config', {})['body'] = task_update_data.body
    if task_update_data.date: updates_for_db.setdefault('workflow_config', {})['date'] = task_update_data.date
    # if task_update_data.interval: updates_for_db.setdefault('workflow_config', {})['interval'] = task_update_data.interval # REMOVED
    if task_update_data.condition: updates_for_db.setdefault('workflow_config', {})['condition'] = task_update_data.condition
    if task_update_data.actionDesc: updates_for_db.setdefault('workflow_config', {})['actionDesc'] = task_update_data.actionDesc
    
    updated_task_dict = await update_scheduler_task_db(db_pool, task_id, updates_for_db)
    if not updated_task_dict:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Scheduler task not found or not updated.")

    # Map to SchedulerTask Pydantic model (similar to create endpoint)
    response_task = SchedulerTask(
        id=str(updated_task_dict.get('id')),
        task_name=updated_task_dict.get('task_name'),
        type=updated_task_dict.get('type'),
        description=updated_task_dict.get('description', updated_task_dict.get('task_name')),
        # trigger_type=updated_task_dict.get('trigger_type'), # REMOVED
        status=updated_task_dict.get('status'),
        last_run_at=updated_task_dict.get('last_run_at'),
        # next_run_at=updated_task_dict.get('next_run_at'), # REMOVED
        workflow_config=updated_task_dict.get('workflow_config'),
        created_at=updated_task_dict.get('created_at'),
        updated_at=updated_task_dict.get('updated_at'),
        to=updated_task_dict.get('workflow_config', {}).get('to'),
        subject=updated_task_dict.get('workflow_config', {}).get('subject'),
        body=updated_task_dict.get('workflow_config', {}).get('body'),
        date=updated_task_dict.get('workflow_config', {}).get('date'),
        # interval=updated_task_dict.get('workflow_config', {}).get('interval'), # REMOVED
        condition=updated_task_dict.get('workflow_config', {}).get('condition'),
        actionDesc=updated_task_dict.get('workflow_config', {}).get('actionDesc')
    )
    return response_task

@app.post("/api/scheduler/task/{task_id}/pause")
async def pause_scheduler_task(task_id: str, request: Request): # Changed task_id to str
    '''
    Pauses or resumes a scheduler task by toggling its status between 'active' and 'paused'.

    :param task_id: The ID of the scheduler task to pause/resume.
    :type task_id: str
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task is not found (404) or if the update fails (500).
    :returns: The new status of the task and its ID.
    :rtype: Dict[str, Union[str, int]]
    '''
    db_pool = request.app.state.db
    # Fetch current task to determine new status
    tasks_from_db = await get_scheduler_tasks_db(db_pool)
    current_task_dict = next((task for task in tasks_from_db if task.get('id') == task_id), None) # Compare str with str

    if not current_task_dict:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    current_status = current_task_dict.get('status')
    new_status = "paused" if current_status == "active" else "active"
    
    updated_task = await update_scheduler_task_db(db_pool, task_id, {"status": new_status})
    if not updated_task:
        # This might indicate a concurrent modification or other issue
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update task status.")
    return {"status": new_status, "id": task_id}

@app.delete("/api/scheduler/task/{task_id}")
async def delete_scheduler_task_endpoint(task_id: str, request: Request): # Changed task_id to str
    '''
    Deletes a scheduler task.

    :param task_id: The ID of the scheduler task to delete.
    :type task_id: str
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task is not found or deletion fails (404).
    :returns: A confirmation message.
    :rtype: Dict[str, Union[bool, str]]
    '''
    db_pool = request.app.state.db
    deleted = await delete_scheduler_task_db(db_pool, task_id)
    if not deleted:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail="Task not found or could not be deleted.")
    return {"ok": True, "message": f"Task {task_id} deleted successfully."}

# Settings Endpoints
@app.get("/api/settings", response_model=SettingsData)
async def get_settings_endpoint(request: Request):
    '''
    Retrieves the current application settings.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: The application settings.
    :rtype: SettingsData
    '''
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
async def save_settings(settings_data: SettingsData, request: Request):
    '''
    Saves application settings.

    :param settings_data: The settings data to save.
    :type settings_data: SettingsData
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    # save_settings_db expects a dictionary
    await save_settings_db(db_pool, settings_data.model_dump())
    return {"status": "success", "message": "Settings saved successfully"}

# User Management Endpoints
@app.post("/api/users/add", response_model=User)
async def addUser(user_create_request: CreateUserRequest, request: Request):
    '''
    Adds a new user to the system.

    :param user_create_request: The details of the user to create.
    :type user_create_request: CreateUserRequest
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If a user with the same email already exists (400) or if an unexpected error occurs (500).
    :returns: The created user object (without password hash).
    :rtype: User
    '''
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
        return created_user
    except UniqueViolationError:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=f"User with email {user_create_request.email} already exists.")
    except Exception as e:
        logger.error(f"Error creating user {user_create_request.email}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while creating the user.")

@app.put("/api/users/{user_identifier}/set", response_model=User)
async def setUser(user_identifier: Union[int, str], user_update_request: UpdateUserRequest, request: Request):
    '''
    Updates an existing user's details.

    The user can be identified by either their ID (int) or email (str).
    If 'password' is provided in the request, it will be hashed before saving.

    :param user_identifier: The ID (int) or email (str) of the user to update.
    :type user_identifier: Union[int, str]
    :param user_update_request: The data to update for the user.
    :type user_update_request: UpdateUserRequest
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If user identifier is invalid (400), user not found (404),
                           email conflict (400), or unexpected error (500).
    :returns: The updated user object (without password hash).
    :rtype: User
    '''
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
        return updated_user
    except UniqueViolationError: # If email is being changed and it collides
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=f"Another user with the new email already exists.")
    except Exception as e:
        logger.error(f"Error updating user {user_identifier}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred while updating the user: {str(e)}")

@app.delete("/api/users/{user_identifier}")
async def deleteUser(user_identifier: Union[int, str], request: Request):
    '''
    Deletes a user from the system.

    The user can be identified by either their ID (int) or email (str).

    :param user_identifier: The ID (int) or email (str) of the user to delete.
    :type user_identifier: Union[int, str]
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If user identifier is invalid (400) or user not found (404).
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
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
    return {"status": "success", "message": f"User with identifier '{user_identifier}' deleted successfully."}

@app.get("/api/users", response_model=List[User])
async def list_users(request: Request):
    '''
    Lists all users in the system.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of user objects (without password hashes).
    :rtype: List[User]
    '''
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
    '''
    Saves a Google access token for a user.

    Note: The request body `data` is expected to be a dictionary with a "token" key.

    :param email: The email of the user for whom to save the token.
    :type email: str
    :param data: A dictionary containing the token, e.g., `{"token": "user_access_token"}`.
    :type data: dict
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If token is missing (400), user not found (404), or update fails (500).
    :returns: A status confirmation.
    :rtype: Dict[str, str]
    '''
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
    return {"status": "ok"}

@app.get("/oauth2callback")
async def oauth2callback_endpoint(request: Request, code: str = Query(...), state: str = Query(None)):
    '''
    Handles the OAuth2 callback from Google.

    Exchanges the authorization code for tokens, extracts user ID from the state,
    and stores the tokens in the database for the user.
    Redirects the user back to the frontend settings page with auth status.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :param code: The authorization code provided by Google.
    :type code: str
    :param state: The state parameter, expected to contain the user ID.
    :type state: Optional[str]
    :raises HTTPException: If OAuth client configuration is missing (500).
    :returns: A RedirectResponse to the frontend settings page.
    :rtype: RedirectResponse
    '''
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
        logger.info(f"user ID {user_id}. Refresh token available: {refresh_token is not None}")
        
        await update_user_google_tokens_db(db_pool, user_id, access_token, refresh_token)
        return RedirectResponse(url="http://localhost:5173/settings?auth=success")
    except Exception as e:
        logger.error(f"Error during OAuth token exchange or DB update for user ID {user_id}: {e}")
        return RedirectResponse(url="http://localhost:5173/settings?auth=failure_token_exchange")
    

@app.get("/api/oauth-config")
def get_oauth_config():
    '''Retrieves the Google OAuth client configuration.

    This is used by the frontend to initialize the Google Login flow.

    :raises HTTPException: If the config file is not found (404) or if there's an error reading/parsing it (500).
    :returns: The OAuth client configuration.
    :rtype: JSONResponse
    '''
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







@app.get("/api/gmail/auth-url")
async def get_gmail_auth_url(request: Request): # request argument might not be needed if user_id is hardcoded/mocked
    '''Generates the Gmail OAuth authorization URL.

    The generated URL includes a state parameter with an appended user ID (currently placeholder '1').
    This URL is intended for the frontend to initiate the Google OAuth flow.

    :param request: The FastAPI request object (currently unused for user_id, but good practice to include).
    :type request: Request
    :returns: A dictionary containing the "auth_url".
    :rtype: Dict[str, str]
    '''
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
    '''Provides the frontend with the Google OAuth URL required by the MCP server for Gmail access.

    This URL initiates the Google OAuth flow with the necessary scopes for Gmail modification.

    :returns: A dictionary containing the "auth_url".
    :rtype: Dict[str, str]
    '''
    # The correct Google OAuth URL for MCP authentication
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?access_type=offline&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.modify&response_type=code&client_id=539932302105-i8gd0gqhokgqtohnc9v7k1ug2j53lkhd.apps.googleusercontent.com&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Foauth2callback"
    logger.info(f"Providing Google OAuth URL for MCP: {auth_url}")
    return {"auth_url": auth_url}

# Add endpoint to handle MCP callback and save token
@app.get("/mcpcallback")
async def mcp_callback_endpoint(request: Request, token: str = Query(...), user_email: str = Query(...)):
    '''
    Handles the callback from the MCP server after user authentication.

    Saves the MCP token for the specified user and redirects to the frontend settings page.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :param token: The MCP token provided by the MCP server.
    :type token: str
    :param user_email: The email of the user associated with this MCP authentication.
    :type user_email: str
    :returns: A RedirectResponse to the frontend settings page with MCP auth status.
    :rtype: RedirectResponse
    '''
    db_pool = request.app.state.db
    user = await get_user_by_email_db(db_pool, user_email)
    if user:
        success = await update_user_mcp_token_db(db_pool, user_email, token)
        if success:
            logger.info(f"MCP token saved successfully for user: {user_email}")
            return RedirectResponse(url="http://localhost:5173/settings?mcpauth=success")
        else:
            logger.error(f"Failed to update MCP token for user: {user_email}")
            return RedirectResponse(url="http://localhost:5173/settings?mcpauth=failure_db_update")
    else:
        logger.error(f"User not found for MCP callback: {user_email}")
        return RedirectResponse(url="http://localhost:5173/settings?mcpauth=failure_user_not_found")

# Processing Task Endpoints
@app.get("/api/processing_tasks", response_model=List[ProcessingTask])
async def get_processing_tasks_endpoint(request: Request):
    '''
    Retrieves a list of all processing tasks.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of processing task objects.
    :rtype: List[ProcessingTask]
    '''
    db_pool = request.app.state.db
    tasks_data = await get_processing_tasks_db(db_pool)
    return [ProcessingTask(**task) for task in tasks_data]

@app.post("/api/processing_tasks/{task_id}/validate")
async def validate_task_endpoint(task_id: int, request: Request):
    '''
    Marks a processing task as 'validated'.

    :param task_id: The ID of the task to validate.
    :type task_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task is not found or update fails (404).
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    # update_task_status_db calls log_task_action_db internally
    updated = await update_task_status_db(db_pool, task_id, 'validated', user="user_api")
    if not updated:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Task with id {task_id} not found or not updated.")
    return {"status": "success", "message": f"Task {task_id} marked as validated."}

@app.post("/api/processing_tasks/{task_id}/abort")
async def abort_task_endpoint(task_id: int, request: Request):
    '''
    Marks a processing task as 'aborted'.

    :param task_id: The ID of the task to abort.
    :type task_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task is not found or update fails (404).
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    updated = await update_task_status_db(db_pool, task_id, 'aborted', user="user_api")
    if not updated:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Task with id {task_id} not found or not updated.")
    return {"status": "success", "message": f"Task {task_id} marked as aborted."}

@app.post("/api/tasks/{task_id}/status") # Note: path uses /api/tasks/ not /api/processing_tasks/
async def set_task_status_endpoint(task_id: int, status_request: SetTaskStatusRequest, request: Request):
    '''
    Sets the status of a specific task.

    :param task_id: The ID of the task to update.
    :type task_id: int
    :param status_request: The request body containing the new status.
    :type status_request: SetTaskStatusRequest
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the task is not found or update fails (404).
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    updated = await update_task_status_db(db_pool, task_id, status_request.status, user="user_api")
    if not updated:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Task with id {task_id} not found or not updated.")
    return {"status": "success", "message": f"Task {task_id} status updated to {status_request.status}."}

# Document Endpoints
@app.delete("/api/documents/{document_id}")
async def delete_document_endpoint(document_id: int, request: Request):
    '''
    Deletes a document by its ID.

    :param document_id: The ID of the document to delete.
    :type document_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the document is not found (404) or if deletion fails (500).
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
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
    return {"status": "ok", "message": f"Document {document_id} deleted successfully from database."}

@app.get("/api/documents", response_model=List[Document])
async def get_documents_endpoint(request: Request):
    '''
    Retrieves a list of all documents.

    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of document objects.
    :rtype: List[Document]
    '''
    db_pool = request.app.state.db
    documents_list = await get_documents_db(db_pool)
    # Ensure the Document model is correctly mapping fields from get_documents_db
    return [Document(**doc) for doc in documents_list]

@app.get("/api/documents/{document_id}/content")
async def get_document_content_endpoint(document_id: int, request: Request):
    '''
    Retrieves the content of a specific document.

    The content is returned as a FileResponse, allowing inline display or download.

    :param document_id: The ID of the document to retrieve content for.
    :type document_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the document or its content is not found (404),
                           or if there's an error decoding the content (500).
    :returns: The document content as a file response.
    :rtype: Response
    '''
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

@app.get("/api/emails/{email_id}/documents", response_model=List[Document])
async def get_documents_by_email_endpoint(email_id: int, request: Request):
    '''
    Retrieves a list of all documents associated with a specific email ID.

    :param email_id: The ID of the email whose documents to retrieve.
    :type email_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :returns: A list of document objects associated with the email.
    :rtype: List[Document]
    '''
    db_pool = request.app.state.db
    documents_list = await get_documents_by_email_id_db(db_pool, email_id)
    # Ensure the Document model is correctly mapping fields from get_documents_by_email_id_db
    return [Document(**doc) for doc in documents_list]

# Scheduler Control Endpoints
@app.post("/api/scheduler/start")
async def start_scheduler_endpoint(request: Request):
    '''
    Starts the agent scheduler.

    :param request: The FastAPI request object.
    :type request: Request
    :raises HTTPException: If the scheduler is not available or initialized (500).
    :returns: The current status of the scheduler ('running').
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    if hasattr(request.app.state, 'scheduler') and request.app.state.scheduler:
        request.app.state.scheduler.start()
        logger.info("Agent scheduler started via API request.")
        return {"status": "running"}
    logger.error("Attempted to start scheduler, but scheduler not found in app.state.")
    raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler not available or not initialized.")

@app.post("/api/scheduler/stop")
async def stop_scheduler_endpoint(request: Request):
    '''
    Stops the agent scheduler and cancels all its tasks.

    :param request: The FastAPI request object.
    :type request: Request
    :raises HTTPException: If the scheduler is not available or initialized (500).
    :returns: The current status of the scheduler ('stopped').
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    if hasattr(request.app.state, 'scheduler') and request.app.state.scheduler:
        request.app.state.scheduler.cancel_all()
        logger.info("Agent scheduler stopped and tasks cancelled via API request.")
        return {"status": "stopped"}
    logger.error("Attempted to stop scheduler, but scheduler not found in app.state.")
    raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler not available or not initialized.")

@app.get("/api/scheduler/status")
async def scheduler_status_endpoint(request: Request):
    '''
    Gets the current status of the agent scheduler (running or stopped).

    :param request: The FastAPI request object.
    :type request: Request
    :raises HTTPException: If the scheduler is not available or initialized (500).
    :returns: The current status of the scheduler.
    :rtype: Dict[str, str]
    '''
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


@app.get("/api/users/{user_identifier}/has_google_refresh_token")
async def has_google_refresh_token(user_identifier: Union[int, str], request: Request):
    '''Checks if a Google refresh token is set for the specified user.

    :param user_identifier: The ID (int) or email (str) of the user to check.
    :type user_identifier: Union[int, str]
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If user identifier is invalid (400), user not found (404),
                           or if token is not set (400).
    :returns: A dictionary indicating whether a refresh token exists.
    :rtype: Dict[str, bool]
    '''
    # Determine if identifier is email or ID
    db_pool = request.app.state.db # Added to use request.app.state.db
    if isinstance(user_identifier, str) and "@" in user_identifier:
        condition_column = "email"
    elif isinstance(user_identifier, int) or (isinstance(user_identifier, str) and user_identifier.isdigit()):
        condition_column = "id"
        try:
            user_identifier = int(user_identifier)
        except ValueError:
            raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format. Must be an integer or numeric string.")
    else:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Invalid user identifier. Must be an email string or an integer ID.")
    row = await db_pool.fetchrow(f"SELECT google_refresh_token FROM users WHERE {condition_column} = $1", user_identifier)
    if not row:
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"User with {condition_column} '{user_identifier}' not found.")
    refresh_token = row["google_refresh_token"]
    if not refresh_token or refresh_token.strip() == "" or refresh_token.lower() == "none": # More robust check
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=f"Google refresh token not set for user {user_identifier}.")
    return {"has_refresh_token": True}


@app.delete("/api/emails/{email_id}")
async def delete_email_endpoint(email_id: int, request: Request):
    '''Deletes an email by its ID from the database.

    :param email_id: The ID of the email to delete.
    :type email_id: int
    :param request: The FastAPI request object, used to access the database pool.
    :type request: Request
    :raises HTTPException: If the email is not found (404) or if the deletion result indicates an issue.
    :returns: A status confirmation message.
    :rtype: Dict[str, str]
    '''
    db_pool = request.app.state.db
    # delete_email_from_db returns bool, True if "DELETE 1", False otherwise
    deleted_successfully = await delete_email_from_db(db_pool=db_pool, email_id=email_id)
    if not deleted_successfully:
        # To provide a more specific error, we might need to check if the email exists first.
        # However, delete_email_from_db already handles linked entities.
        # If it returns False, it means the email was not found or an issue occurred.
        # For simplicity, we'll assume not found if delete operation didn't affect rows.
        # A more robust check would be to call get_email_by_id_db first.
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=f"Email with id {email_id} not found or delete operation failed.")
    
    return {"status": "ok", "message": f"Email {email_id} deleted successfully from database."}

@app.post("/api/userinfo")
async def userinfo(request: Request):
    '''Retrieves user information (admin status, roles, Google ID) based on email.

    The email is first attempted to be retrieved from `request.app.state.email`.
    If not found there, it attempts to parse the email from the JSON request body
    (e.g., `{"email": "user@example.com"}`).

    :param request: The FastAPI request object, used to access app state and request body.
    :type request: Request
    :raises HTTPException: If email is not provided in state or body (400),
                           or if JSON body is invalid (400).
    :returns: User information including `is_admin`, `roles`, and `google_id`.
              Returns default values if user not found (as per `check_if_admin_user_exists_db` behavior).
    :rtype: Dict[str, Any]
    '''
    user_email = None
    # Try to get email from request state first
    if hasattr(request.app.state, 'email') and request.app.state.email:
        user_email = request.app.state.email
    else:
        # If not in state, try to parse from request body
        try:
            body = await request.json()
            user_email = body.get("email")
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON body while attempting to get email for /api/userinfo.")
            raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body.")
        
    if not user_email:
        logger.warning("/api/userinfo called without user email in state or body.")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="User email not provided in request state or body.")

    db_pool = request.app.state.db
    user_info_result = await check_if_admin_user_exists_db(db_pool, user_email)
    logger.info(f"Userinfo query for email: {user_email} returned: {user_info_result}")
    return user_info_result

