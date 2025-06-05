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
from backend.tools_wrapper import (
    list_emails, get_email, label_email, send_email, draft_email, read_email, search_emails, modify_email, delete_email, list_email_labels, create_label, update_label, delete_label, get_or_create_label, batch_modify_emails, batch_delete_emails
)
import asyncpg
from backend.agent_ws import agent_websocket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter, HTTPException
import uuid
import datetime
from backend.agent_scheduler import AgentScheduler

# Logging configuration
logging.basicConfig(level=logging.ERROR)

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

# Email/Audit models
class Email(BaseModel):
    id: int
    subject: str
    sender: str
    body: str
    label: Optional[str]

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

class User(BaseModel):
    id: int | None = None
    email: str
    password: str | None = None
    is_admin: bool = False
    roles: list[str] = []

# DB pool
@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.create_pool(DATABASE_URL)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()

# Email endpoints
@app.get("/api/emails", response_model=List[Email])
async def get_emails():
    rows = await app.state.db.fetch("SELECT * FROM emails")
    return [dict(row) for row in rows]

@app.get("/api/emails/{email_id}", response_model=Email)
async def get_email(email_id: int):
    row = await app.state.db.fetchrow("SELECT * FROM emails WHERE id=$1", email_id)
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

scheduler = AgentScheduler()

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
