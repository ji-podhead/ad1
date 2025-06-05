# FastAPI backend for Ornex Mail
# Entry point: main.py

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
from dotenv import load_dotenv
import os
import logging
from tools_wrapper import (
    list_emails, get_email, label_email, send_email, draft_email, read_email, search_emails, modify_email, delete_email, list_email_labels, create_label, update_label, delete_label, get_or_create_label, batch_modify_emails, batch_delete_emails
)
import asyncpg
from agent_ws import agent_websocket
from fastapi import HTTPException
import uuid
import datetime
from agent_scheduler import AgentScheduler
from fastapi.responses import JSONResponse
from fastapi import Request

from backend.email_poller import fetch_new_emails
# Imports for task utilities from email_poller
from backend.email_poller import create_task as util_create_task
from backend.email_poller import link_task_to_email as util_link_task_to_email
from backend.email_poller import create_task_from_email as util_create_task_from_email
from backend.email_poller import email_exists # For validation in task creation

import asyncio
from functools import partial


# Logging configuration
# logging.basicConfig(level=logging.ERROR) # Keep original level
# For more detailed logs from this integration:
logging.basicConfig(level=logging.INFO)
# Consider making the log level configurable if needed
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mailwhisperer")

app = FastAPI()

# CORS for local frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class DocumentMetadata(BaseModel):
    id: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None # Assuming BIGINT from DB fits in int
    created_at: datetime.datetime

class TaskMetadata(BaseModel):
    id: str
    title: str
    status: str
    priority: Optional[str] = None
    due_date: Optional[datetime.datetime] = None

class Email(BaseModel): # Updated Email model
    id: str # Was int, now TEXT from DB
    topic: Optional[str] = None
    sender: str
    recipient: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    received_at: datetime.datetime
    imported_at: datetime.datetime # This field is in the DB schema
    archived: bool = False
    read: bool = False
    labels: Optional[List[str]] = []
    user_id: Optional[int] = None

    documents: Optional[List[DocumentMetadata]] = []
    tasks: Optional[List[TaskMetadata]] = []

class AuditTrail(BaseModel): # Updated AuditTrail
    id: int
    email_id: Optional[str] = None # Was int, now TEXT from DB
    task_id: Optional[str] = None # New
    user_id: Optional[int] = None # From new schema (users.id)
    action: str
    # username: str # Replaced by user_id or details field
    details: Optional[dict] = None # For JSONB details
    timestamp: datetime.datetime # Ensure it's datetime

class SchedulerTask(BaseModel): # Unchanged for now
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

class User(BaseModel):
    id: int | None = None
    email: str
    password: str | None = None
    is_admin: bool = False
    roles: list[str] = []

class Task(BaseModel): # More detailed model for full task CRUD
    id: str
    user_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: Optional[str] = None
    due_date: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    # emails: Optional[List[EmailMetadata]] = [] # If we want to show linked emails here

class TaskCreate(BaseModel): # Model for creating a task
    title: str
    description: Optional[str] = None
    user_id: Optional[int] = None # Who the task is for
    status: str = 'todo'
    priority: str = 'medium'
    due_date: Optional[datetime.datetime] = None
    # Optionally, email_id to link on creation
    email_id_to_link: Optional[str] = None

class TaskUpdate(BaseModel): # Model for updating a task
    title: Optional[str] = None
    description: Optional[str] = None
    user_id: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime.datetime] = None

# DB pool
scheduler = AgentScheduler() # Ensure scheduler is initialized here if not already (it's global in example)

@app.on_event("startup")
async def startup():
    logger.info("Application startup...")
    try:
        app.state.db = await asyncpg.create_pool(DATABASE_URL)
        logger.info("Database pool created.")

        # Schedule the email poller
        async def scheduled_fetch_emails():
            # This local logger is optional, email_poller has its own
            poller_logger = logging.getLogger("email_poller_schedule")
            poller_logger.info("Running scheduled email fetch...")
            if hasattr(app.state, 'db') and app.state.db:
                try:
                    await fetch_new_emails(app.state.db)
                    poller_logger.info("Scheduled email fetch completed.")
                except Exception as e_poll:
                    poller_logger.error(f"Error during scheduled email fetch: {e_poll}", exc_info=True)
            else:
                poller_logger.error("Database pool not available for scheduled email fetch.")

        polling_interval_seconds = 60
        scheduler.schedule_cron(scheduled_fetch_emails, polling_interval_seconds)
        logger.info(f"Scheduled email polling every {polling_interval_seconds} seconds.")

    except Exception as e:
        logger.error(f"Error during application startup: {e}", exc_info=True)
        # Depending on severity, you might want to re-raise or handle differently
        raise

@app.on_event("shutdown")
async def shutdown():
    logger.info("Application shutdown...")
    if scheduler: # Check if scheduler was initialized
        scheduler.cancel_all()
        logger.info("Cancelled all scheduled tasks.")

    if hasattr(app.state, 'db') and app.state.db:
        await app.state.db.close()
        logger.info("Database pool closed.")
    else:
        logger.info("Database pool was not available or already closed.")

# Email endpoints
@app.get("/api/emails", response_model=List[Email])
async def get_emails(): # Replacing old get_emails
    emails_list = []
    try:
        async with app.state.db.acquire() as connection:
            # Fetch base email data
            email_rows = await connection.fetch("SELECT * FROM emails ORDER BY received_at DESC LIMIT 100")

            for row in email_rows:
                email_dict = dict(row)
                email_id = email_dict['id']

                # Fetch associated documents
                doc_rows = await connection.fetch(
                    """SELECT d.id, d.filename, d.content_type, d.size_bytes, d.created_at
                       FROM documents d
                       JOIN email_documents ed ON d.id = ed.document_id
                       WHERE ed.email_id = $1 ORDER BY d.filename""", email_id)
                email_dict['documents'] = [DocumentMetadata(**doc_row) for doc_row in doc_rows]

                # Fetch associated tasks
                task_rows = await connection.fetch(
                    """SELECT t.id, t.title, t.status, t.priority, t.due_date
                       FROM tasks t
                       JOIN email_tasks et ON t.id = et.task_id
                       WHERE et.email_id = $1 ORDER BY t.created_at""", email_id)
                email_dict['tasks'] = [TaskMetadata(**task_row) for task_row in task_rows]

                emails_list.append(Email(**email_dict))
        return emails_list
    except Exception as e:
        logger.error(f"Error fetching emails: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch emails")

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_single_email(email_id: str): # Replacing old get_email, email_id is str
    try:
        async with app.state.db.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM emails WHERE id = $1", email_id)
            if not row:
                raise HTTPException(status_code=404, detail="Email not found")

            email_dict = dict(row)

            # Fetch associated documents
            doc_rows = await connection.fetch(
                """SELECT d.id, d.filename, d.content_type, d.size_bytes, d.created_at
                   FROM documents d
                   JOIN email_documents ed ON d.id = ed.document_id
                   WHERE ed.email_id = $1 ORDER BY d.filename""", email_id)
            email_dict['documents'] = [DocumentMetadata(**doc_row) for doc_row in doc_rows]

            # Fetch associated tasks
            task_rows = await connection.fetch(
                """SELECT t.id, t.title, t.status, t.priority, t.due_date
                   FROM tasks t
                   JOIN email_tasks et ON t.id = et.task_id
                   WHERE et.email_id = $1 ORDER BY t.created_at""", email_id)
            email_dict['tasks'] = [TaskMetadata(**task_row) for task_row in task_rows]

            return Email(**email_dict)
    except HTTPException: # Re-raise HTTPException directly
        raise
    except Exception as e:
        logger.error(f"Error fetching email {email_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch email")

@app.post("/api/emails/{email_id}/label")
async def label_email(email_id: str, label_to_add: str): # Replacing old label_email
    try:
        async with app.state.db.acquire() as connection:
            # Add label to the text array. This appends if not present.
            # COALESCE handles if labels is NULL initially.
            # AND NOT (labels @> ARRAY[$1]) ensures idempotency (label not added if already present)
            await connection.execute(
                """UPDATE emails
                   SET labels = array_append(COALESCE(labels, ARRAY[]::TEXT[]), $1)
                   WHERE id = $2 AND NOT (COALESCE(labels, ARRAY[]::TEXT[]) @> ARRAY[$1]::TEXT[]);""",
                label_to_add, email_id
            )
            # Audit log - adapt to new audit_trail schema
            # This needs user context from auth; for now, user_id is None.
            await connection.execute(
                "INSERT INTO audit_trail (email_id, action, details, user_id, timestamp) VALUES ($1, $2, $3, $4, NOW())",
                email_id,
                "add_label",
                json.dumps({"label": label_to_add}), # Store relevant details as JSON
                None # Placeholder for actual user ID
            )
        return {"status": "ok", "message": f"Label '{label_to_add}' processed for email {email_id}"}
    except Exception as e:
        logger.error(f"Error adding label to email {email_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add label")

@app.get("/api/audit", response_model=List[AuditTrail]) # Ensure this uses the updated AuditTrail model
async def get_audit():
    rows = await app.state.db.fetch("SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT 100")
    return [AuditTrail(**dict(row)) for row in rows] # Use model for consistency


# --- Document API Endpoints ---
@app.get("/api/documents", response_model=List[DocumentMetadata])
async def list_all_documents(email_id: Optional[str] = None):
    try:
        async with app.state.db.acquire() as connection:
            if email_id:
                query = """SELECT d.id, d.filename, d.content_type, d.size_bytes, d.created_at
                           FROM documents d
                           JOIN email_documents ed ON d.id = ed.document_id
                           WHERE ed.email_id = $1 ORDER BY d.created_at DESC"""
                doc_rows = await connection.fetch(query, email_id)
            else:
                query = "SELECT id, filename, content_type, size_bytes, created_at FROM documents ORDER BY created_at DESC LIMIT 100"
                doc_rows = await connection.fetch(query)
            return [DocumentMetadata(**dict(row)) for row in doc_rows]
    except Exception as e:
        logger.error(f"Error listing documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list documents")

@app.get("/api/documents/{document_id}", response_model=DocumentMetadata)
async def get_document_details(document_id: str):
    try:
        async with app.state.db.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT id, filename, content_type, size_bytes, created_at FROM documents WHERE id = $1",
                document_id
            )
            if not row:
                raise HTTPException(status_code=404, detail="Document not found")
            return DocumentMetadata(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch document")

# --- Task API Endpoints ---
@app.post("/api/tasks", response_model=Task, status_code=201)
async def api_create_task(task_data: TaskCreate):
    try:
        if task_data.email_id_to_link:
            # Validate email exists before attempting to link
            # email_exists is already imported via backend.email_poller imports
            if not await email_exists(app.state.db, task_data.email_id_to_link):
                raise HTTPException(status_code=404, detail=f"Email {task_data.email_id_to_link} not found for linking task.")

            task_id = await util_create_task_from_email(
                app.state.db,
                email_id=task_data.email_id_to_link,
                title=task_data.title, description=task_data.description,
                user_id=task_data.user_id, status=task_data.status,
                priority=task_data.priority, due_date=task_data.due_date
            )
        else:
            task_id = await util_create_task(
                app.state.db,
                title=task_data.title, description=task_data.description,
                user_id=task_data.user_id, status=task_data.status,
                priority=task_data.priority, due_date=task_data.due_date
            )

        async with app.state.db.acquire() as connection:
            new_task_row = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if not new_task_row:
                raise HTTPException(status_code=500, detail="Task created but failed to retrieve.")
            return Task(**dict(new_task_row))
    except ValueError as ve: # From create_task_from_email if email not found
            logger.warning(f"Value error creating task: {ve}") # Log it as warning
            raise HTTPException(status_code=400, detail=str(ve)) # Return 400 for bad request (e.g. invalid email_id)
    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")

@app.get("/api/tasks", response_model=List[Task])
async def api_list_tasks(email_id: Optional[str] = None, status: Optional[str] = None, user_id: Optional[int] = None):
    query_conditions = []
    query_params = []

    # Start with base query for tasks table aliased as 't'
    base_query = "SELECT t.id, t.user_id, t.title, t.description, t.status, t.priority, t.due_date, t.created_at, t.updated_at FROM tasks t"

    param_idx = 1 # Positional argument index for SQL query

    if email_id:
        base_query += f" JOIN email_tasks et ON t.id = et.task_id"
        query_conditions.append(f"et.email_id = ${param_idx}")
        query_params.append(email_id)
        param_idx += 1

    if status:
        query_conditions.append(f"t.status = ${param_idx}")
        query_params.append(status)
        param_idx += 1
    if user_id is not None: # Check for None explicitly for integer user_id
        query_conditions.append(f"t.user_id = ${param_idx}")
        query_params.append(user_id)
        param_idx += 1

    if query_conditions:
        base_query += " WHERE " + " AND ".join(query_conditions)

    base_query += " ORDER BY t.created_at DESC LIMIT 100"

    try:
        async with app.state.db.acquire() as connection:
            task_rows = await connection.fetch(base_query, *query_params)
            return [Task(**dict(row)) for row in task_rows]
    except Exception as e:
        logger.error(f"Error listing tasks with query '{base_query}' and params '{query_params}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list tasks")

@app.get("/api/tasks/{task_id}", response_model=Task)
async def api_get_task(task_id: str):
    try:
        async with app.state.db.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if not row:
                raise HTTPException(status_code=404, detail="Task not found")
            return Task(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch task")

@app.put("/api/tasks/{task_id}", response_model=Task)
async def api_update_task(task_id: str, task_update_data: TaskUpdate):
    update_fields = task_update_data.model_dump(exclude_unset=True) # Get only provided fields

    if not update_fields:
        raise HTTPException(status_code=400, detail="No update data provided")

    set_clauses = []
    query_params = []
    param_idx = 1

    for key, value in update_fields.items():
        set_clauses.append(f"{key} = ${param_idx}")
        query_params.append(value)
        param_idx += 1

    # The DB trigger on `tasks` table handles `updated_at = NOW()` automatically.
    # No need to add it here unless the trigger is removed or a different behavior is desired.

    query_params.append(task_id) # For the WHERE id = ${param_idx}

    update_query = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ${param_idx} RETURNING *"

    try:
        async with app.state.db.acquire() as connection:
            updated_task_row = await connection.fetchrow(update_query, *query_params)
            if not updated_task_row:
                # This could also mean the task exists but no fields were actually changed
                # if all values in task_update_data matched existing values.
                # However, fetchrow would still return the row.
                # So, not found is the primary reason for no row.
                raise HTTPException(status_code=404, detail="Task not found")
            return Task(**dict(updated_task_row))
    except HTTPException: # Re-raise if it's an HTTPException (like 404)
        raise
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update task: {str(e)}")

@app.delete("/api/tasks/{task_id}", status_code=204)
async def api_delete_task(task_id: str):
    try:
        async with app.state.db.acquire() as connection:
            # `ON DELETE CASCADE` in `email_tasks` table handles unlinking from emails.
            # `ON DELETE SET NULL` in `audit_trail` for `task_id` handles audit entries.
            result = await connection.execute("DELETE FROM tasks WHERE id = $1", task_id)

            # result from execute for DELETE is a string like 'DELETE 1' (number of rows deleted)
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Task not found")

            # Optional: Log deletion to audit_trail if not handled by DB triggers or if more detail is needed
            # try:
            #     await connection.execute(
            #         "INSERT INTO audit_trail (action, details, user_id, task_id) VALUES ($1, $2, $3, $4)",
            #         "task_deleted",
            #         json.dumps({"deleted_task_id": task_id}),
            #         None, # Placeholder for actual user_id from auth context
            #         task_id # Associate audit with the deleted task_id
            #     )
            # except Exception as audit_e:
            #     logger.error(f"Failed to log task deletion to audit trail for task {task_id}: {audit_e}", exc_info=True)

        # For 204 No Content, FastAPI expects no return value (or return None)
        return
    except HTTPException: # Re-raise if it's an HTTPException (like 404)
        raise
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")

# WebSocket for agent chat (MCP integration)
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    await agent_websocket(websocket)

# scheduler = AgentScheduler() # This was moved to global scope before startup()

# In-memory task store for demo (replace with DB in production)
scheduled_tasks: List[SchedulerTask] = []

@app.get("/api/scheduler/tasks", response_model=List[SchedulerTask])
async def get_scheduler_tasks():
    return scheduled_tasks

@app.post("/api/scheduler/task", response_model=SchedulerTask)
async def create_scheduler_task(task: SchedulerTask):
    task.id = str(uuid.uuid4())
    scheduled_tasks.append(task)
    # TODO: Start real scheduling logic with AgentScheduler
    return task

@app.post("/api/scheduler/task/{task_id}/pause")
async def pause_scheduler_task(task_id: str):
    for t in scheduled_tasks:
        if t.id == task_id:
            t.status = "paused" if t.status == "active" else "active"
            return {"status": t.status}
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/api/scheduler/task/{task_id}")
async def delete_scheduler_task(task_id: str):
    global scheduled_tasks
    scheduled_tasks = [t for t in scheduled_tasks if t.id != task_id]
    return {"ok": True}

@app.post("/api/users")
async def create_user(user: User):
    # Insert user into DB
    try:
        row = await app.state.db.fetchrow(
            "INSERT INTO users (email, password, is_admin, roles) VALUES ($1, $2, $3, $4) RETURNING id, email, is_admin, roles",
            user.email, user.password or '', user.is_admin, user.roles
        )
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/users")
async def list_users():
    rows = await app.state.db.fetch("SELECT id, email, is_admin, roles FROM users")
    return [dict(row) for row in rows]

@app.get("/api/oauth-config")
def get_oauth_config():
    # Path was corrected in a previous step, should be 'auth/gcp-oauth.keys.json'
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
    row = await app.state.db.fetchrow("SELECT is_admin, roles FROM users WHERE email=$1", email)
    if not row:
        return {"is_admin": False, "roles": []}
    return {"is_admin": row["is_admin"], "roles": row["roles"]}
