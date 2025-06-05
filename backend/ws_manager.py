from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
from dataclasses import dataclass
import asyncio
import json

@dataclass
class Task:
    id: str
    status: str
    progress: float
    children: List['Task']

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.tasks: Dict[str, Task] = {}
        self.respondMsgs = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]

    async def send_personal_message(self, session_id: str, message: dict):
        print("Sending personal message to", session_id)
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)
        else:
            raise WebSocketDisconnect(code=404, reason="Session not found")

    async def broadcast_task_update(self, task_id: str, status: str, progress: float):
        update = {"task_id": task_id, "status": status, "progress": progress}
        for ws in self.active_connections.values():
            await ws.send_json(update)

    async def receive_text(self, uuid, websocket: WebSocket):
        """Receives text from the WebSocket in a parallel async task and returns a promise."""
        try:
            self.respondMsgs[uuid] = None
            response = await websocket.receive_text()
            print(f"respond uuid: {uuid} response: {response}")
            return response
        except WebSocketDisconnect:
            return None
        # TODO: This method seems unused by agent_ws.py (which uses websocket.receive_text() directly). Review for removal.

async def stream_task_progress(manager: ConnectionManager, task_id: str):
    while True:
        task = manager.tasks.get(task_id)
        if task:
            yield json.dumps({
                "task_id": task.id,
                "status": task.status,
                "progress": task.progress
            })
        await asyncio.sleep(1)
