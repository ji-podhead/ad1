# FastAPI backend for Ornex Mail
# Entry point: main.py

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
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
from tools_wrapper import (
    list_emails, get_email, label_email, send_email, draft_email, read_email, search_emails, modify_email, delete_email, list_email_labels, create_label, update_label, delete_label, get_or_create_label, batch_modify_emails, batch_delete_emails
)
import asyncpg
from agent_ws import agent_websocket
from fastapi import HTTPException
import uuid
import datetime
from agent_scheduler import AgentScheduler, check_new_emails # Import check_new_emails
from fastapi.responses import JSONResponse
from fastapi import Request

# Logging configuration
logging.basicConfig(level=logging.ERROR)

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mailwhisperer")

app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# CORS for local frontend dev
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

class AuditTrail(BaseModel):
    id: int
    email_id: int
    action: str
    user: str
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

class User(BaseModel):
    id: int | None = None
    email: str
    password: str | None = None
    is_admin: bool = False
    roles: list[str] = []

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


class SetTaskStatusRequest(BaseModel):
    status: str

# DB pool
@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.create_pool(DATABASE_URL)
    # Initialize and store scheduler
    app.state.scheduler = AgentScheduler() # Use the global scheduler instance or app.state.scheduler
    # Schedule the email checking job
    # Make sure check_new_emails is an async function that accepts db_pool
    app.state.scheduler.schedule_cron(check_new_emails, 60, app.state.db)
    print("Scheduled email checking job to run every 60 seconds.")

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
    rows = await app.state.db.fetch("SELECT id, subject, sender, body, label, type FROM emails")
    return [dict(row) for row in rows]

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_email(email_id: int):
    row = await app.state.db.fetchrow("SELECT id, subject, sender, body, label, type FROM emails WHERE id=$1", email_id)
    return dict(row)

@app.post("/api/emails/{email_id}/label")
async def label_email(email_id: int, label: str):
    await app.state.db.execute("UPDATE emails SET label=$1 WHERE id=$2", label, email_id)
    # Audit log
    await app.state.db.execute(
        "INSERT INTO audit_trail (email_id, action, user, timestamp) VALUES ($1, $2, $3, NOW())",
        email_id, f"label:{label}", "user",  # TODO: real user
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
    return [dict(row) for row in rows]

@app.post("/api/scheduler/task", response_model=SchedulerTask)
async def create_scheduler_task(task: SchedulerTask, request: Request):
    task.id = str(uuid.uuid4())
    # Ensure default status if not provided, though Pydantic model has default
    if task.status is None:
        task.status = "active"

    await request.app.state.db.execute(
        """
        INSERT INTO scheduler_tasks (id, type, description, status, nextRun, to_email, subject, body, date_val, interval_seconds, condition, actionDesc, trigger_type, workflow_config, workflow_name)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        """,
        task.id, task.type, task.description, task.status, task.nextRun,
        task.to, task.subject, task.body, task.date, task.interval,
        task.condition, task.actionDesc, task.trigger_type, task.workflow_config, task.workflow_name
    )
    # TODO: Actual scheduling logic with app.state.scheduler needs to be wired up here
    # For example, if task.type == 'email', schedule it.
    # This part is complex as it requires translating DB stored task back to scheduler actions.
    # Current AgentScheduler doesn't have a direct way to load tasks from DB.
    return task

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
    # TODO: Update actual scheduler if task was active/paused (AgentScheduler might need methods for this)
    return {"status": new_status}

@app.delete("/api/scheduler/task/{task_id}")
async def delete_scheduler_task(task_id: str, request: Request):
    result = await request.app.state.db.execute("DELETE FROM scheduler_tasks WHERE id = $1", task_id)
    if result == "DELETE 0": # Check if any row was deleted
        raise HTTPException(status_code=404, detail="Task not found")
    # TODO: Unscheduling logic from AgentScheduler needed here
    return {"ok": True}

# Define request model for creating a user, explicitly requiring a password
class CreateUserRequest(BaseModel):
    email: str
    password: str
    is_admin: bool = False
    roles: list[str] = []

@app.post("/api/users/add", response_model=User)
async def addUser(user_create_request: CreateUserRequest):
    hashed_password = pwd_context.hash(user_create_request.password)
    try:
        query = """
            INSERT INTO users (email, password, is_admin, roles)
            VALUES ($1, $2, $3, $4)
            RETURNING id, email, is_admin, roles
        """
        row = await app.state.db.fetchrow(
            query,
            user_create_request.email,
            hashed_password,
            user_create_request.is_admin,
            user_create_request.roles
        )
        if row:
            return User(**dict(row))
        else:
            # This case should ideally not be reached if INSERT RETURNING works as expected
            raise HTTPException(status_code=500, detail="Failed to create user.")
    except UniqueViolationError: # Specific error for duplicate email
        raise HTTPException(status_code=400, detail=f"User with email {user_create_request.email} already exists.")
    except Exception as e:
        # Generic error for other issues
        logging.error(f"Error creating user {user_create_request.email}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while creating the user.")

class UpdateUserRequest(BaseModel):
    email: Optional[str] = None # Allow changing email, though be cautious with this
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    roles: Optional[list[str]] = None

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
        f"SELECT id, email, password, is_admin, roles FROM users WHERE {condition_column} = $1",
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

    if not update_fields:
        # Return existing user data if no changes are requested
        return User(**existing_user)

    set_clauses = ", ".join([f"{field} = ${i+2}" for i, field in enumerate(update_fields.keys())])
    query = f"UPDATE users SET {set_clauses} WHERE {condition_column} = $1 RETURNING id, email, is_admin, roles"

    try:
        updated_user_row = await app.state.db.fetchrow(query, user_identifier, *update_fields.values())
        if updated_user_row:
            return User(**dict(updated_user_row))
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

    # Check if user exists before attempting deletion (optional, but good for clear error messages)
    user_exists = await app.state.db.fetchval(
        f"SELECT EXISTS(SELECT 1 FROM users WHERE {condition_column} = $1)",
        user_identifier
    )
    if not user_exists:
        raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found.")

    try:
        result = await app.state.db.execute(
            f"DELETE FROM users WHERE {condition_column} = $1",
            user_identifier
        )
        if result == "DELETE 0": # Should ideally be caught by the check above
            raise HTTPException(status_code=404, detail=f"User with {condition_column} '{user_identifier}' not found during delete, though existed moments before.")
        return {"status": "success", "message": f"User with {condition_column} '{user_identifier}' deleted successfully."}
    except Exception as e:
        logging.error(f"Error deleting user {user_identifier}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while deleting the user.")

@app.get("/api/users")
async def list_users():
    rows = await app.state.db.fetch("SELECT id, email, is_admin, roles FROM users")
    return [dict(row) for row in rows]

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
    row = await app.state.db.fetchrow("SELECT is_admin, roles FROM users WHERE email=$1", email)
    if not row:
        return {"is_admin": False, "roles": []}
    return {"is_admin": row["is_admin"], "roles": row["roles"]}


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
        t.workflow_type
    FROM tasks t
    LEFT JOIN emails e ON t.email_id = e.id
    ORDER BY t.created_at DESC;
    """
    rows = await request.app.state.db.fetch(query)
    return [dict(row) for row in rows]


async def log_task_action(db_pool, task_id: int, action: str, user: str = "system_user"):
    """Helper function to log task actions to audit_trail."""
    # Fetch email_id associated with the task_id for more complete audit logging
    email_id_record = await db_pool.fetchrow("SELECT email_id FROM tasks WHERE id = $1", task_id)
    email_id = email_id_record['email_id'] if email_id_record else None

    await db_pool.execute(
        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
        email_id, f"task_{action}:task_id_{task_id}", user, # TODO: Real user
    )

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

    await log_task_action(request.app.state.db, task_id, "validate")
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

    await log_task_action(request.app.state.db, task_id, "abort")
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
    await log_task_action(request.app.state.db, task_id, f"status_set_to_{status_request.status}")

    # Optionally, fetch and return the updated task
    # updated_task = await request.app.state.db.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    # return dict(updated_task)
    return {"status": "success", "message": f"Task {task_id} status updated to {status_request.status}."}
